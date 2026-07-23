"""
LLM 기반 법률상담 구조화 모델 - 신규 Google GenAI SDK (google-genai) 실시간 호출 코드

흐름:
  상담 텍스트 --(few-shot 포함 프롬프트)--> Gemini Structured Outputs (response_schema)
             --(pydantic 파싱/검증)--> AIAnalysisSchema
             --(검증 실패 시 재시도)--> 최종 반환
"""

import json
import os
from pathlib import Path
from typing import List, Type

from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

from app.schemas.analysis import AIAnalysisSchema
from app.services.prompts import SYSTEM_PROMPT

_DATA_PATH = Path(__file__).parents[1] / "data" / "few_shot_examples.json"

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    """신규 google-genai Client 인스턴스 싱글톤 관리"""
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError(".env 파일에 GEMINI_API_KEY가 설정되어 있지 않습니다.")
        _client = genai.Client(api_key=api_key)
    return _client


def _prepare_gemini_schema(pydantic_model: Type[BaseModel]) -> dict:
    """
    Gemini API에서 거부하는 'additional_properties', 'title', '$schema' 등의
    비표준 키를 제거하고 $ref 참조를 풀어 Gemini 호환 JSON 스키마 dict를 생성합니다.
    """
    raw_schema = pydantic_model.model_json_schema()
    root_defs = raw_schema.get("$defs", {})

    def resolve_and_clean(node):
        if isinstance(node, dict):
            # $ref 참조가 있는 경우 $defs에서 찾아 인라인으로 해제
            if "$ref" in node:
                ref_key = node["$ref"].split("/")[-1]
                if ref_key in root_defs:
                    resolved = resolve_and_clean(root_defs[ref_key])
                    merged = {k: v for k, v in node.items() if k != "$ref"}
                    merged.update(resolved)
                    return merged

            cleaned = {}
            for k, v in node.items():
                # Gemini API에서 지원하지 않는 스키마 메타 필드 제거
                if k in (
                    "$defs",
                    "additionalProperties",
                    "additional_properties",
                    "title",
                    "$schema",
                    "default",
                ):
                    continue
                cleaned[k] = resolve_and_clean(v)
            return cleaned
        elif isinstance(node, list):
            return [resolve_and_clean(item) for item in node]
        return node

    return resolve_and_clean(raw_schema)


def _load_few_shot_contents() -> List[dict]:
    """few_shot_examples.json -> google-genai contents 대화 배열로 변환"""
    raw = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    contents: List[dict] = []
    for ex in raw["examples"]:
        contents.append({"role": "user", "parts": [{"text": ex["input"]}]})
        contents.append(
            {
                "role": "model",
                "parts": [{"text": json.dumps(ex["output"], ensure_ascii=False)}],
            }
        )
    return contents


# 모듈 로드 시 1회만 파싱
_FEW_SHOT_CONTENTS = _load_few_shot_contents()
_GEMINI_CLEANED_SCHEMA = _prepare_gemini_schema(AIAnalysisSchema)


def build_contents(consultation_text: str) -> List[dict]:
    """few-shot 대화 흐름 뒤에 실제 입력 상담글을 붙여 대화 배열 생성"""
    contents: List[dict] = list(_FEW_SHOT_CONTENTS)
    contents.append({"role": "user", "parts": [{"text": consultation_text}]})
    return contents


def analyze_consultation(
    consultation_text: str,
    model_name: str = "gemini-2.5-flash-lite",
    max_retries: int = 2,
) -> AIAnalysisSchema:
    """
    상담 텍스트를 받아 신규 google-genai SDK로 AIAnalysisSchema 구조화 분석을 수행.
    """
    client = _get_client()
    contents = build_contents(consultation_text)

    last_error: str | None = None
    raw_content: str = ""

    for attempt in range(max_retries + 1):
        if last_error:
            # 검증 실패 시 모델 답변과 피드백을 이어서 전달
            current_contents = contents + [
                {"role": "model", "parts": [{"text": raw_content}]},
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": (
                                f"방금 출력이 Pydantic 스키마 검증에 실패했습니다: {last_error}\n"
                                "반드시 아래 9개 필드를 하나도 빠짐없이 완벽한 JSON으로 출력하세요:\n"
                                "- summary, case_type, case_subtype, urgency_level, eligibility\n"
                                "- extracted_json, missing_info_json, checklist_json, timeline_json"
                            )
                        }
                    ],
                },
            ]
        else:
            current_contents = contents

        # 정제된 Gemini 전용 스키마 전달
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=_GEMINI_CLEANED_SCHEMA,
            temperature=0.1,
            max_output_tokens=2048,
        )

        response = client.models.generate_content(
            model=model_name,
            contents=current_contents,
            config=config,
        )

        raw_content = response.text

        try:
            return AIAnalysisSchema.model_validate_json(raw_content)
        except ValidationError as e:
            last_error = str(e)
            if attempt == max_retries:
                raise

    raise RuntimeError("unreachable")