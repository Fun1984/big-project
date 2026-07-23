"""
agents/missing_data/graph.py

누락자료 / 추가조사 필요항목 감지 LangGraph 파이프라인.

- candidate_generation : case_type과 무관하게 범용 프롬프트로 "누락 후보"를 자유롭게 생성.
  eligibility/analyze 결과(relief_review_checklist)를 최소 기준선(힌트)으로 삼되,
  원본 텍스트를 다시 훑어 그 외 누락도 함께 찾는다.
- validation           : 각 후보를 원본 텍스트와 재대조하여 confidence(0~1)를 매긴다
  (할루시네이션/오탐 체크). 최종 채택 여부는 config.CONFIDENCE_THRESHOLD로 코드에서 결정.
- 두 단계 모두 확정적 법률판단을 내리지 않으며, 결과는 참고자료임을 전제로 한다 (HITL 원칙).

main.py에서는 이 모듈의 `missing_data_graph`만 가져다 쓰면 된다:
    from app.agents.missing_data.graph import missing_data_graph
    result_state = await missing_data_graph.ainvoke(initial_state)
"""

from typing import List

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END

from . import config
from .modal import (
    MissingDataState,
    CandidateList,
    ValidatedList,
    MissingItemValidated,
)


# ---------------------------------------------------------------------------
# 1. LLM 클라이언트 (모듈 로드 시 1회만 생성)
# ---------------------------------------------------------------------------

llm = ChatOpenAI(model=config.MODEL_NAME, temperature=0)

candidate_llm = llm.with_structured_output(CandidateList, method=config.STRUCTURED_METHOD)
validation_llm = llm.with_structured_output(ValidatedList, method=config.STRUCTURED_METHOD)


# ---------------------------------------------------------------------------
# 2. 프롬프트
# ---------------------------------------------------------------------------

COMMON_PRINCIPLE = """
[공통 원칙]
- 당신은 대한법률구조공단 내부 상담 지원 도구의 정보 추출 보조 역할만 수행합니다.
- 사건유형(case_type)과 무관하게 동일한 기준으로 판단하세요 (유형별 특칙 적용 금지).
- "~에 해당한다", "~이다" 같은 단정적 법률판단 표현을 쓰지 말고 참고용 표현만 사용하세요.
- 이 결과는 참고자료이며, 최종 판단은 담당 변호사/공익법무관이 수행합니다 (HITL).
"""

CANDIDATE_PROMPT = COMMON_PRINCIPLE + """
[추출 목적]
아래 사건 정보를 보고, 이후 단계(서식 작성, 구조검토 4대 기준 판단)에 필요하지만
아직 확보되지 않았거나 확정되지 않은 항목의 후보를 찾으세요.

- 구조검토 4대 기준: 구조대상자 여부 / 승소가능성 / 집행가능성 / 구조타당성
- relief_review_checklist에 이미 드러난 미비 사항(evidence_status, required_evidence,
  각 항목의 review_note)은 최소 기준선으로 삼되, 원본 텍스트를 다시 훑어 그 외에
  빠진 것도 찾으세요.
- 각 후보에는 항목명(item), 종류(증빙/사실관계), 이유(reason)를 함께 답하세요.

[사건유형]
{case_type}

[사건 자료 (요약 + 상세 + 추출된 첨부내용)]
{consult_text}

[구조검토 체크리스트 결과]
{relief_review_checklist}
"""

VALIDATION_PROMPT = COMMON_PRINCIPLE + """
[검증 목적]
아래는 "누락되었다"고 제시된 후보 항목 목록과, 그 사건의 원본 자료입니다.
각 후보에 대해 원본 자료를 다시 확인하여:

1. 정말로 원본 자료 어디에도 해당 정보/자료가 없는지 재검토하세요.
   (이미 원문에 있는데 후보 생성 단계에서 놓친 경우 confidence를 낮게 주세요)
2. confidence(0~1)를 매기세요.
   - 1.0에 가까움: 원본을 다시 봐도 확실히 없음 / 명백히 필요한 정보
   - 0.5 근처: 애매함 (일부 암시는 있으나 확정 자료는 없음)
   - 0에 가까움: 사실 원본에 이미 있거나, 이 사건에 꼭 필요한 항목이 아님
3. evidence_check_note에 재확인 근거를 간단히 남기세요.

[원본 사건 자료]
{consult_text}

[누락 후보 목록]
{candidates}
"""


# ---------------------------------------------------------------------------
# 3. 헬퍼
# ---------------------------------------------------------------------------

def _consult_text(state: MissingDataState) -> str:
    """rescue_check.graph._consult_text와 동일 로직.
    모듈 간 결합을 피하기 위해 의도적으로 중복 구현함 (3줄 수준이라 재사용 이득이 적음)."""
    summary = state.get("summary", "")
    details = state.get("details", "")
    extracted = state.get("extracted_content", "")
    return f"[요약]\n{summary}\n\n[상세]\n{details}\n\n[추출된 첨부내용]\n{extracted}"


# ---------------------------------------------------------------------------
# 4. LangGraph 노드
# ---------------------------------------------------------------------------

async def candidate_generation_node(state: MissingDataState) -> dict:
    text = _consult_text(state)
    prompt = CANDIDATE_PROMPT.format(
        case_type=state.get("case_type", ""),
        consult_text=text,
        relief_review_checklist=state.get("relief_review_checklist", {}),
    )
    result: CandidateList = await candidate_llm.ainvoke(
        [SystemMessage(content=prompt), HumanMessage(content=text)]
    )
    return {"candidate_missing_items": [c.model_dump() for c in result.candidates]}


async def validation_node(state: MissingDataState) -> dict:
    text = _consult_text(state)
    prompt = VALIDATION_PROMPT.format(
        consult_text=text,
        candidates=state.get("candidate_missing_items", []),
    )
    result: ValidatedList = await validation_llm.ainvoke(
        [SystemMessage(content=prompt), HumanMessage(content=text)]
    )

    # 코드 레벨 threshold 적용 -- 실질적인 "임계치 조정" 지점 (config.CONFIDENCE_THRESHOLD)
    final_items: List[dict] = [
        v.model_dump()
        for v in result.validated
        if v.confidence >= config.CONFIDENCE_THRESHOLD
    ]
    return {"missing_items": final_items}


# ---------------------------------------------------------------------------
# 5. 그래프 조립 (순차 구조 — rescue_check와 동일 패턴, 안정성 우선)
# ---------------------------------------------------------------------------

_graph_builder = StateGraph(MissingDataState)

_graph_builder.add_node("candidate_generation", candidate_generation_node)
_graph_builder.add_node("validation", validation_node)

_graph_builder.add_edge(START, "candidate_generation")
_graph_builder.add_edge("candidate_generation", "validation")
_graph_builder.add_edge("validation", END)

missing_data_graph = _graph_builder.compile()
