"""
KLAC 법률상담 구조화 분석 LangGraph 백본.
Colab notebook(01_02__klac_case_analysis_backbone__after.ipynb)의 로직을 그대로 이식.
"""
import os
from typing import List, Literal, TypedDict
from urllib.parse import urlparse

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from . import config  # noqa: F401  (OPENAI_API_KEY 등 환경변수를 미리 로드/검증)
from .multimodal import (
    determine_file_category,
    download_to_temp_from_s3,
    extract_text_from_audio_video,
    extract_text_from_caption,
    extract_text_from_document,
)

# ---------------------------------------------------------------------------
# 1. 구조화 출력 스키마
# ---------------------------------------------------------------------------


class CaseTypeResult(BaseModel):
    """사건 유형 분류 결과 (참고용 — 최종 확정은 담당자 검토 필요)"""

    case_type: Literal["임금체불", "개인회생", "개인파산", "불법사금융피해", "기타"] = Field(
        description="상담 요약/상세 내용/추출 콘텐츠에 기반한 사건 유형 분류 결과"
    )
    reason: str = Field(
        description="분류 근거를 1~2문장으로 요약. 단정적 표현('~이다', '~에 해당한다') 대신 "
        "'~로 판단됨', '~로 보임' 등 참고용 표현 사용"
    )


class EmergencyResult(BaseModel):
    """긴급도 분류 결과 (참고용 — 최종 확정은 담당자 검토 필요)"""

    case_emergency_ratio: float = Field(
        ge=0.0, le=1.0, description="0.0(비긴급)~1.0(매우 긴급) 사이의 긴급도 점수"
    )
    case_emergency_level: Literal["상", "중", "하"] = Field(
        description="긴급도 등급. 상: 생명/신체 위험, 소멸시효 임박, 강제집행 임박 등 즉시 대응 필요 "
        "/ 중: 수일~수주 내 대응 필요 / 하: 특별한 시한 압박 없음"
    )
    reason: str = Field(description="긴급도 판단 근거 1~2문장")


# ---------------------------------------------------------------------------
# 2. LangGraph State
# ---------------------------------------------------------------------------


class ConsultState(TypedDict, total=False):
    """
    주의(중복 이슈 관련): 아래 필드들은 LangGraph 노드 간에 값을 주고받기 위한
    "그래프 내부용" 필드다. summary/details/extracted_content/case_type/
    case_emergency_* 는 각 노드가 다음 노드에 값을 넘기려고 State에 쌓아두는 것일 뿐,
    최종적으로 API가 응답하는 값은 아니다.

    combine_output_node가 이 필드들을 case_analysis 하나로 모으고,
    run_case_analysis()는 최종 응답으로 raw_input + case_analysis만 반환한다.
    (state 전체를 그대로 반환하면 case_type 등이 최상위와 case_analysis 양쪽에
    중복 노출되는 문제가 있었음 — ToBe에서 수정)
    """

    raw_input: dict

    summary: str
    details: str
    submitted_file_link: List[str]
    consult_day: str

    extracted_content: List[str]  # 파일별 추출 텍스트 배열. extracted_content_detail과 동일 인덱스로 매칭됨
    extracted_content_detail: list

    case_type: str
    case_type_reason: str

    case_emergency_ratio: float
    case_emergency_level: str
    case_emergency_reason: str

    case_analysis: dict


# ---------------------------------------------------------------------------
# 3. LLM 클라이언트 (모듈 로드 시 1회만 생성 -> 요청마다 재생성 안 함)
# ---------------------------------------------------------------------------

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
case_type_llm = llm.with_structured_output(CaseTypeResult)
emergency_llm = llm.with_structured_output(EmergencyResult)


# ---------------------------------------------------------------------------
# 4. 프롬프트
# ---------------------------------------------------------------------------

CASE_TYPE_SYSTEM_PROMPT = """당신은 대한법률구조공단 내부 상담 지원 도구로서, 상담 내용을 바탕으로
사건 유형을 분류하는 보조 역할을 수행합니다.

[중요 원칙]
- 이 분류는 상담원/변호사/공익법무관의 업무를 보조하기 위한 참고 자료일 뿐이며,
  최종 사건 유형 확정 및 법률적 판단은 반드시 사람이 수행합니다.
- "~에 해당한다", "~이다"와 같은 단정적 법률판단 표현을 쓰지 말고,
  "~로 보임", "~가능성이 있음" 등 참고용 표현을 사용하세요.
- 상담 요약/상세 내용뿐 아니라, 첨부파일(녹취록/문서 등)에서 추출된 내용이 함께 제공될 수 있으니
  두 내용을 종합해서 판단하세요.

[분류 대상 및 기준]
1. 임금체불: 임금, 급여, 퇴직금, 수당 등을 정당한 사유 없이 지급받지 못한 사례
   예) "3개월째 월급을 못 받았고 사장님이 연락을 피합니다" → 임금체불
2. 개인회생: 정기적 수입은 있으나 과다채무로 정상적인 상환이 어려운 경우
   예) "월급은 받고 있지만 카드빚, 대출이 너무 많아 매달 갚기 힘듭니다" → 개인회생
3. 개인파산: 소득이 없거나 매우 적어 채무 상환 자체가 사실상 불가능한 경우
   예) "실직 상태이고 재산도 없어서 빚을 갚을 방법이 없습니다" → 개인파산
4. 불법사금융피해: 미등록 대부업체 이용, 법정 최고금리 초과, 협박성 채권추심 등 피해 사례
   예) "미등록 사채업자에게 연 200% 이자를 요구받고 폭언과 협박을 당하고 있습니다" → 불법사금융피해
5. 기타: 위 4개 항목에 명확히 해당하지 않는 경우

위 5개 중 하나로만 분류하세요."""


EMERGENCY_SYSTEM_PROMPT = """당신은 대한법률구조공단 내부 상담 지원 도구로서, 상담 내용의 긴급도를
분석하는 보조 역할을 수행합니다.

[중요 원칙]
- 이 분석은 참고용이며, 실제 대응 우선순위 결정은 상담원/변호사가 최종 판단합니다.
- 단정적 표현 대신 참고용 표현을 사용하세요.
- 상담 요약/상세 내용뿐 아니라, 첨부파일에서 추출된 내용이 함께 제공될 수 있으니 종합해서 판단하세요.

[긴급도 판단 기준 (참고 신호)]
- 상 (0.7~1.0): 생명·신체에 대한 위험(폭행/협박 지속 등), 소멸시효·제척기간 임박,
  강제집행(가압류/경매 등) 임박, 형사고소 기한 임박 등 즉시 대응이 필요한 경우
  예) "내일 모레 강제집행이 예정되어 있습니다" → 상, ratio 0.9 내외
- 중 (0.3~0.7 미만): 수일~수 주 내 대응이 필요하나 즉각적 위험은 아닌 경우
  예) "다음 달 소송 기일이 잡혀 있습니다" → 중, ratio 0.5 내외
- 하 (0.0~0.3 미만): 특별한 시한 압박이 없고 정보 제공 목적에 가까운 경우
  예) "제도가 궁금해서 문의드립니다" → 하, ratio 0.1 내외

사건 유형(case_type)과 상담 요약/상세 내용/추출 콘텐츠를 함께 고려하여 case_emergency_ratio(0.0~1.0)와
case_emergency_level(상/중/하)을 산출하세요."""


# ---------------------------------------------------------------------------
# 5. 노드 함수
# ---------------------------------------------------------------------------


def parse_input_node(state: ConsultState) -> dict:
    """Input 노드: 원본 {"content": {...}} 구조를 State 필드로 펼침"""
    content = state["raw_input"]["content"]

    file_links = content.get("summited_file_link", [])
    if isinstance(file_links, str):
        file_links = [file_links] if file_links else []
    elif file_links is None:
        file_links = []

    return {
        "summary": content.get("summary", ""),
        "details": content.get("details", ""),
        "submitted_file_link": file_links,
        "consult_day": content.get("consult_day", ""),
    }


def process_multimodal_content_node(state: ConsultState) -> dict:
    """submitted_file_link(array)에 있는 파일들을 S3에서 받아 STT/문서추출 처리.
    개별 파일 처리 실패가 전체 파이프라인을 막지 않는다.

    extracted_content는 array[str]로, extracted_content_detail과 반드시 동일한
    길이/순서쌍(같은 인덱스 = 같은 파일)을 유지한다. 실제 텍스트 내용을 확인할 수
    없는 경우 아래 기준으로 값을 채운다.
      - 추출은 시도됐지만 결과 텍스트가 비어있음                    -> "내용없음"
      - 다운로드/추출 중 예외 발생, 미지원 파일 형식, 인식 불가 등  -> "파일 오류"
    """
    links = state.get("submitted_file_link") or []
    if not links:
        return {"extracted_content": [], "extracted_content_detail": []}

    extracted_texts = []
    detail_logs = []

    for link in links:
        log = {"file_link": link, "status": "failed", "file_type": None, "error": None}
        text_entry = "파일 오류"

        try:
            local_path, content_type = download_to_temp_from_s3(link)
            ext = os.path.splitext(urlparse(link).path)[1].lower()
            category = determine_file_category(link, content_type)
            log["file_type"] = category

            if category == "audio_video":
                text = extract_text_from_audio_video(local_path)
            elif category == "caption":
                text = extract_text_from_caption(local_path)
            elif category == "document":
                text = extract_text_from_document(local_path, ext)
            elif category == "unsupported_hwp":
                log["status"] = "unsupported"
                log["error"] = "HWP/HWPX는 kordoc 변환 파이프라인 연동이 필요하여 이번 백본에서는 미구현"
                detail_logs.append(log)
                extracted_texts.append("파일 오류")
                continue
            else:
                log["status"] = "unsupported"
                log["error"] = f"인식할 수 없는 파일 유형 (content-type: {content_type})"
                detail_logs.append(log)
                extracted_texts.append("파일 오류")
                continue

            if text:
                text_entry = text
                log["status"] = "success"
            else:
                text_entry = "내용없음"
                log["status"] = "empty"
                log["error"] = "텍스트 추출 결과가 비어있음"

        except Exception as e:
            log["error"] = str(e)
            text_entry = "파일 오류"

        detail_logs.append(log)
        extracted_texts.append(text_entry)

    return {
        "extracted_content": extracted_texts,
        "extracted_content_detail": detail_logs,
    }


def _build_context_text(state: ConsultState) -> str:
    parts = [
        f"[상담 요약]\n{state.get('summary', '')}",
        f"[상세 내용]\n{state.get('details', '')}",
    ]
    extracted_list = state.get("extracted_content") or []
    # "내용없음"/"파일 오류"는 실제 콘텐츠가 아니므로 LLM 프롬프트에는 포함하지 않는다.
    usable_texts = [t for t in extracted_list if t not in ("내용없음", "파일 오류")]
    if usable_texts:
        parts.append("[첨부파일에서 추출된 내용]\n" + "\n\n".join(usable_texts))
    return "\n\n".join(parts)


def classify_case_type_node(state: ConsultState) -> dict:
    user_msg = f"[상담일] {state.get('consult_day', '')}\n\n" + _build_context_text(state)
    result: CaseTypeResult = case_type_llm.invoke(
        [SystemMessage(content=CASE_TYPE_SYSTEM_PROMPT), HumanMessage(content=user_msg)]
    )
    return {"case_type": result.case_type, "case_type_reason": result.reason}


def classify_emergency_node(state: ConsultState) -> dict:
    user_msg = f"[사건 유형(참고용 분류 결과)] {state.get('case_type', '')}\n\n" + _build_context_text(state)
    result: EmergencyResult = emergency_llm.invoke(
        [SystemMessage(content=EMERGENCY_SYSTEM_PROMPT), HumanMessage(content=user_msg)]
    )
    return {
        "case_emergency_ratio": result.case_emergency_ratio,
        "case_emergency_level": result.case_emergency_level,
        "case_emergency_reason": result.reason,
    }


def combine_output_node(state: ConsultState) -> dict:
    """최종 결과 결합 노드: State에 flat하게 흩어져 있던 필드들(extracted_content,
    extracted_content_detail, case_type, case_type_reason, case_emergency_*)을
    case_analysis 하나로 모두 모은다.

    주의: 이 노드가 반환하는 case_analysis가 "최종적으로 노출할 결과의 전부"가 되도록
    구성한다. run_case_analysis()에서 최상위 State 전체가 아니라 raw_input + case_analysis만
    반환하기 때문에, 여기서 빠뜨린 필드는 최종 응답에 나타나지 않는다. (AS-IS에서는 이 값들이
    최상위 State 필드로도 남아있고 case_analysis 안에도 다시 들어가서 중복 노출되는 문제가 있었음)
    """
    case_analysis = {
        "extracted_content": state.get("extracted_content", []),
        "extracted_content_detail": state.get("extracted_content_detail", []),
        "case_type": state.get("case_type"),
        "case_type_reason": state.get("case_type_reason"),
        "case_emergency_ratio": state.get("case_emergency_ratio"),
        "case_emergency_level": state.get("case_emergency_level"),
        "case_emergency_reason": state.get("case_emergency_reason"),
    }
    return {"case_analysis": case_analysis}


# ---------------------------------------------------------------------------
# 6. Graph 구성 및 컴파일 (모듈 로드 시 1회만 컴파일)
# ---------------------------------------------------------------------------

graph_builder = StateGraph(ConsultState)

graph_builder.add_node("parse_input", parse_input_node)
graph_builder.add_node("process_multimodal_content", process_multimodal_content_node)
graph_builder.add_node("classify_case_type", classify_case_type_node)
graph_builder.add_node("classify_emergency", classify_emergency_node)
graph_builder.add_node("combine_output", combine_output_node)

graph_builder.add_edge(START, "parse_input")
graph_builder.add_edge("parse_input", "process_multimodal_content")
graph_builder.add_edge("process_multimodal_content", "classify_case_type")
graph_builder.add_edge("classify_case_type", "classify_emergency")
graph_builder.add_edge("classify_emergency", "combine_output")
graph_builder.add_edge("combine_output", END)

klac_graph = graph_builder.compile()


def run_case_analysis(input_data: dict) -> dict:
    """FastAPI 핸들러에서 호출하는 진입점 함수.

    내부 LangGraph State는 노드 간 데이터 전달을 위해 summary/details/extracted_content/
    case_type/case_emergency_* 등을 flat 필드로 계속 들고 있지만, 그건 어디까지나 그래프
    내부 구현 디테일이다. 외부(FastAPI 응답 / 프론트/DB 저장)에 나가는 최종 결과는
    raw_input과 case_analysis 두 필드로만 구성해서, 같은 값이 최상위와 case_analysis
    양쪽에 중복 노출되지 않도록 한다. (ToBe 구조)
    """
    state = klac_graph.invoke({"raw_input": input_data})
    return {
        "raw_input": state.get("raw_input"),
        "case_analysis": state.get("case_analysis"),
    }
