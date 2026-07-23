# services/form_recommender.py — 서식 추천 모듈
#
# 역할: AI 분석 결과(구조화 JSON) → 추천 서식 목록(recommended_forms_json)
# 사용:
#   from services.form_recommender import recommend
#   result = recommend(analysis)   # {"recommendations": [...], "candidates_count": N}
#
# FastAPI 연결 예:
#   POST /recommend-forms  → recommend(body)

import json
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI()

# 서식 매핑 (helplaw24 공식 분류). ai-api 루트에 위치.
MAPPING_FILE = Path(__file__).resolve().parent.parent / "helplaw24_서식_카테고리_매핑.json"

_mapping_cache = None
def _load_mapping():
    global _mapping_cache
    if _mapping_cache is None:
        _mapping_cache = json.load(open(MAPPING_FILE, encoding="utf-8"))
    return _mapping_cache


def get_candidates(case_type: str, case_subtype: str = None) -> list:
    """대분류/소분류로 서식 후보를 좁힌다 (규칙 기반, 1단계)."""
    mapping = _load_mapping()
    if case_subtype:
        hits = [m for m in mapping if m["sub"] == case_subtype]
        if hits:
            return hits
    return [m for m in mapping if m["main"] == case_type]


RECOMMEND_PROMPT = """너는 법률구조공단 상담을 보조하는 서식 추천 도구다.
상담 분석 결과(사건요약, 추출정보)와 서식 후보 목록을 보고,
이 민원인에게 지금 필요한 서식을 우선순위로 추천한다.

규칙:
1. 반드시 후보 목록에 있는 서식명만 추천한다. 새로 지어내지 않는다.
2. 최대 3개까지, 상황에 가장 맞는 순서로.
3. 각 서식마다 "이 상담의 어떤 사실 때문에 이 서식인지" 근거를
   summary/extracted의 구체적 내용을 인용해 한 문장으로 쓴다.
4. 후보 중 적합한 것이 없으면 recommendations를 빈 배열로 하고
   reason_if_empty에 이유를 쓴다.

출력은 JSON만:
{
  "recommendations": [
    {"rank": 1, "form_name": "서식명 그대로", "reason": "근거 한 문장"},
    {"rank": 2, ...}
  ],
  "reason_if_empty": ""
}"""


def recommend(analysis: dict) -> dict:
    """분석 결과를 받아 서식을 추천한다.

    analysis 필수 키: case_type, case_subtype, summary, extracted_json
    반환: {"recommendations": [...], "reason_if_empty": "", "candidates_count": N}
    """
    candidates = get_candidates(analysis.get("case_type"), analysis.get("case_subtype"))
    if not candidates:
        return {"recommendations": [], "reason_if_empty": "해당 유형의 서식 후보가 없습니다.",
                "candidates_count": 0}

    user_msg = (
        f"[상담 분석 결과]\n"
        f"사건유형: {analysis.get('case_type')} > {analysis.get('case_subtype')}\n"
        f"요약: {analysis.get('summary')}\n"
        f"추출정보: {json.dumps(analysis.get('extracted_json', {}), ensure_ascii=False)}\n\n"
        f"[서식 후보 목록]\n" + "\n".join(f"- {c['name']}" for c in candidates)
    )
    resp = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": RECOMMEND_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    result = json.loads(resp.choices[0].message.content)
    result["candidates_count"] = len(candidates)
    return result


# ── 독립 실행 테스트 ──
if __name__ == "__main__":
    mock = {
        "case_type": "친족",
        "case_subtype": "양육비",
        "summary": "협의이혼 후 상대방이 매월 50만원 양육비를 6개월째 미지급. "
                   "총 300만원 연체. 상대방은 회사 재직 중인 급여소득자.",
        "extracted_json": {
            "청구인": {"이름": "김영희"}, "상대방": {"이름": "이철수", "직업": "회사원"},
            "월양육비": 500000, "미지급개월": 6,
        },
    }
    out = recommend(mock)
    print(json.dumps(out, ensure_ascii=False, indent=2))