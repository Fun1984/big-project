"""
agents/missing_data/config.py

누락자료/추가조사 필요항목 감지에 필요한 설정값만 모아둔 모듈.
pydantic 스키마나 LangGraph 관련 로직은 여기 두지 않음 (그건 modal.py / graph.py 담당).

TODO (팀 확인 필요):
1) CONFIDENCE_THRESHOLD: 실사용 피드백(상담원/변호사가 "이거 있었는데 왜 빠졌냐" 하는 케이스) 쌓이면
   재조정 필요. 오탐(사실 있는데 없다고 우김)이 많으면 올리고, 미탐(진짜 필요한 걸 놓침)이
   많으면 내릴 것.
2) rescue_check.config.MODEL_NAME과 동일한 값을 쓰되, 이 노드만 별도로 모델을 바꿔 실험하고
   싶을 수 있어 KLAC_MISSING_DATA_MODEL 환경변수를 따로 둠 (미설정 시 rescue_check와 동일값).
"""

import os

# ---------------------------------------------------------------------------
# LLM 관련 설정
# ---------------------------------------------------------------------------

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
MODEL_NAME = os.environ.get("KLAC_MISSING_DATA_MODEL", os.environ.get("KLAC_LLM_MODEL", "gpt-4o-mini"))

# rescue_check.config와 동일한 사유로 function_calling 고정
# (strict json_schema는 Optional/List 조합에서 400 에러를 낼 수 있음)
STRUCTURED_METHOD = "function_calling"


# ---------------------------------------------------------------------------
# 검증(validation) 단계 신뢰도 임계치
# ---------------------------------------------------------------------------

# 검증 노드가 매긴 confidence(0~1)가 이 값 이상인 후보만 최종 missing_items로 채택.
# temperature가 아니라 "이 값"을 조정하는 것이 실질적인 임계치 튜닝 지점임.
CONFIDENCE_THRESHOLD: float = 0.7
