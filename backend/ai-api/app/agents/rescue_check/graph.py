"""
agents/rescue_check/graph.py

법률구조 대상 여부 판단(Rule Engine) + 구조검토 체크리스트 LangGraph 파이프라인.

- 구조대상자 여부만 Rule Engine이 대상/비대상/판단보류를 자동 산출한다.
- 승소가능성/집행가능성/구조타당성은 AI가 결론을 내지 않고 체크리스트용 신호만 추출한다.
  최종 확정은 반드시 조사담당변호사가 수행한다 (HITL 원칙).
- 5개 신호 추출 LLM 호출은 asyncio.gather로 동시에 실행해 지연시간을 줄인다.
- 그래프 자체는 순차 구조(extract_all_signals -> eligibility_rule -> build_checklist)로
  구성해 안정성을 우선한다 (어제 사건유형/긴급도 파이프라인과 동일한 패턴).

main.py에서는 이 모듈의 `eligibility_graph`만 가져다 쓰면 된다:
    from agents.rescue_check.graph import eligibility_graph
    result_state = await eligibility_graph.ainvoke(initial_state)
"""

import asyncio
from datetime import date, datetime
from typing import Optional, List

from dateutil.relativedelta import relativedelta
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END

from . import config
from .modal import (
    ConsultState,
    IncomePropertySignal,
    SpecialStatusSignal,
    WinnabilitySignal,
    ExecutabilitySignal,
    ReliefAppropriatenessSignal,
    EligibilityRuleResult,
    ReliefReviewChecklist,
)


# ---------------------------------------------------------------------------
# 1. LLM 클라이언트 (모듈 로드 시 1회만 생성 -> 요청마다 재생성 안 함)
# ---------------------------------------------------------------------------

llm = ChatOpenAI(model=config.MODEL_NAME, temperature=0)

income_signal_llm = llm.with_structured_output(IncomePropertySignal, method=config.STRUCTURED_METHOD)
status_signal_llm = llm.with_structured_output(SpecialStatusSignal, method=config.STRUCTURED_METHOD)
winnability_llm = llm.with_structured_output(WinnabilitySignal, method=config.STRUCTURED_METHOD)
executability_llm = llm.with_structured_output(ExecutabilitySignal, method=config.STRUCTURED_METHOD)
appropriateness_llm = llm.with_structured_output(ReliefAppropriatenessSignal, method=config.STRUCTURED_METHOD)


# ---------------------------------------------------------------------------
# 2. 프롬프트
# ---------------------------------------------------------------------------

COMMON_PRINCIPLE = """
[공통 원칙]
- 당신은 대한법률구조공단 내부 상담 지원 도구의 정보 추출 보조 역할만 수행합니다.
- 최종 법률적 판단(대상 여부, 승소가능성, 집행가능성, 구조타당성)은 절대 스스로 내리지 말고,
  상담 내용에 드러난 "신호"만 정직하게 추출하세요. 언급이 없으면 반드시 null / 판단 불가로 표기하세요.
- "~에 해당한다", "~이다" 같은 단정적 법률판단 표현을 쓰지 말고, "~로 보임", "~로 언급됨" 형태만 사용하세요.
- 상담 요약/상세/추출된 첨부파일 내용을 종합해서 신호를 추출하세요.
"""

INCOME_PROPERTY_PROMPT = COMMON_PRINCIPLE + """
[추출 대상]
기초생활수급자/차상위계층 여부, 가구원 수, 월평균소득 추정치, 소상공인 사건 맥락 여부,
언급된 소득 관련 소명자료(소득증빙/가족관계증명/장애인 증명 등)를 추출하세요.
"""

SPECIAL_STATUS_PROMPT = COMMON_PRINCIPLE + """
[추출 대상 카테고리]
소년소녀가장, 모자가정, 장애인, 국내거주 저소득 외국인근로자(임금/퇴직금/산재 사건 한정),
법원 소송구조결정 피구조자, 국선변호 대상 피의자·피고인, 그 외.
상담 내용이 위 카테고리 중 어디에도 명확히 해당하지 않으면 "그 외"만 반환하세요.
"""

WINNABILITY_PROMPT = COMMON_PRINCIPLE + """
[추출 대상]
제출/언급된 자료 종류, 구조대상자의 주관적 사정 요약(원문 인용 금지, 1~2문장 요약만),
소멸시효 기산일 및 적용 가능 시효기간(추출 가능한 경우만), 청구권 존재/부존재 시사, 사실관계 입증 가능성 시사.
"""

EXECUTABILITY_PROMPT = COMMON_PRINCIPLE + """
[추출 대상]
상대방(피고)의 재산 상태에 대한 언급 - 무재산자/소재불명/재산 확인 여부.
"""

APPROPRIATENESS_PROMPT = COMMON_PRINCIPLE + """
[추출 대상]
사건 성격(단순 개인간 이해다툼 vs 사회적 약자 보호), 남소 우려/감정적 분쟁 여부,
대안적 권리구제 수단 언급 여부, 소액 사건 여부, 업무범위 외 사유(법인/종중 관련 등).
"""


# ---------------------------------------------------------------------------
# 3. Rule Engine 함수
# ---------------------------------------------------------------------------

def apply_eligibility_rules(
    income_signal: IncomePropertySignal,
    status_signal: SpecialStatusSignal,
) -> EligibilityRuleResult:
    reasons: List[str] = []
    income_met: Optional[bool] = None
    applied_ratio: Optional[float] = None

    if income_signal.is_basic_livelihood_recipient_mentioned:
        income_met = True
        reasons.append("기초생활수급자")
    elif income_signal.is_near_poverty_class_mentioned:
        income_met = True
        reasons.append("차상위계층")
    elif income_signal.monthly_income_estimate is not None:
        threshold = config.get_income_threshold(
            income_signal.household_size, income_signal.is_small_business_context
        )
        applied_ratio = (
            config.INCOME_THRESHOLD_RATIO_SMALL_BIZ
            if income_signal.is_small_business_context
            else config.INCOME_THRESHOLD_RATIO_DEFAULT
        )
        if threshold is None:
            income_met = None  # 가구원수 미상 or 해당 연도 고시표 없음 -> 계산 불가
        else:
            income_met = income_signal.monthly_income_estimate <= threshold
            if income_met:
                reasons.append("월평균소득 기준 이하")

    status_categories = status_signal.matched_categories
    only_other = status_categories == ["그 외"]
    status_met = bool(status_categories) and not only_other
    if status_met:
        reasons.extend([c for c in status_categories if c != "그 외"])

    required_evidence = config.map_reasons_to_required_evidence(reasons)
    provided = set(income_signal.income_evidence_mentioned + status_signal.status_evidence_mentioned)
    missing = [e for e in required_evidence if e not in provided]

    if not required_evidence:
        evidence_status = "확인불가"
    elif not missing:
        evidence_status = "충족"
    elif provided:
        evidence_status = "미비"
    else:
        evidence_status = "확인불가"

    if income_met or status_met:
        eligible = "대상"
    elif only_other or (income_met is None and not status_categories):
        eligible = "판단보류"
    else:
        eligible = "비대상"

    reason_text = ", ".join(reasons) if reasons else "해당 사유 없음"
    return EligibilityRuleResult(
        income_criterion_met=income_met,
        status_criterion_met=status_met,
        matched_reasons=reasons,
        required_evidence=required_evidence,
        evidence_status=evidence_status,
        eligible=eligible,
        applied_income_threshold_ratio=applied_ratio,
        judgment_note=f"{reason_text}을(를) 근거로 {eligible}로 보임",
    )


def compute_statute_of_limitations(
    signal: WinnabilitySignal, case_type: Optional[str] = None
) -> WinnabilitySignal:
    """소멸시효 완성 여부 계산.

    LLM이 기산일(limitation_start_date)만 추출한 경우, 시효기간은
    사건유형별 config.STATUTE_OF_LIMITATIONS_MAP 기본값을 사용한다.
    """
    period = signal.limitation_period_years
    if period is None and case_type is not None:
        period = config.STATUTE_OF_LIMITATIONS_MAP.get(case_type)

    if not signal.limitation_start_date or period is None:
        signal.statute_of_limitations_flag = "계산 불가"
        return signal
    try:
        start = datetime.strptime(signal.limitation_start_date, "%Y-%m-%d").date()
    except ValueError:
        signal.statute_of_limitations_flag = "계산 불가"
        return signal

    years = int(period)
    months = int(round((period - years) * 12))
    expiry = start + relativedelta(years=years, months=months)

    signal.statute_of_limitations_flag = "완성 명백" if date.today() > expiry else "미완성"
    return signal


# ---------------------------------------------------------------------------
# 4. LangGraph 노드
# ---------------------------------------------------------------------------

def _consult_text(state: ConsultState) -> str:
    summary = state.get("summary", "")
    details = state.get("details", "")
    extracted = state.get("extracted_content", "")
    return f"[요약]\n{summary}\n\n[상세]\n{details}\n\n[추출된 첨부내용]\n{extracted}"


async def extract_all_signals_node(state: ConsultState) -> dict:
    """5개 신호 추출 LLM 호출을 asyncio.gather로 동시에 실행 (지연시간 단축)."""
    text = _consult_text(state)
    (
        income_signal,
        status_signal,
        winnability_signal,
        executability_signal,
        appropriateness_signal,
    ) = await asyncio.gather(
        income_signal_llm.ainvoke([SystemMessage(content=INCOME_PROPERTY_PROMPT), HumanMessage(content=text)]),
        status_signal_llm.ainvoke([SystemMessage(content=SPECIAL_STATUS_PROMPT), HumanMessage(content=text)]),
        winnability_llm.ainvoke([SystemMessage(content=WINNABILITY_PROMPT), HumanMessage(content=text)]),
        executability_llm.ainvoke([SystemMessage(content=EXECUTABILITY_PROMPT), HumanMessage(content=text)]),
        appropriateness_llm.ainvoke([SystemMessage(content=APPROPRIATENESS_PROMPT), HumanMessage(content=text)]),
    )

    winnability_signal = compute_statute_of_limitations(winnability_signal, state.get("case_type"))

    return {
        "income_property_signal": income_signal.model_dump(),
        "special_status_signal": status_signal.model_dump(),
        "winnability_signal": winnability_signal.model_dump(),
        "executability_signal": executability_signal.model_dump(),
        "appropriateness_signal": appropriateness_signal.model_dump(),
    }


def eligibility_rule_node(state: ConsultState) -> dict:
    income_signal = IncomePropertySignal(**state["income_property_signal"])
    status_signal = SpecialStatusSignal(**state["special_status_signal"])
    result = apply_eligibility_rules(income_signal, status_signal)
    return {"eligibility_result": result.model_dump()}


def build_checklist_node(state: ConsultState) -> dict:
    checklist = ReliefReviewChecklist(
        eligibility=EligibilityRuleResult(**state["eligibility_result"]),
        winnability=WinnabilitySignal(**state["winnability_signal"]),
        executability=ExecutabilitySignal(**state["executability_signal"]),
        appropriateness=ReliefAppropriatenessSignal(**state["appropriateness_signal"]),
        checklist_summary_for_lawyer=(
            f"[구조대상자 여부] {state['eligibility_result']['eligible']} "
            f"({state['eligibility_result']['judgment_note']})\n"
            f"[승소가능성] {state['winnability_signal']['review_note']}\n"
            f"[집행가능성] {state['executability_signal']['review_note']}\n"
            f"[구조타당성] {state['appropriateness_signal']['review_note']}\n"
            f"※ 위 내용은 AI 참고 자료이며, 최종 확정은 조사담당변호사가 수행합니다."
        ),
    )
    return {"relief_review_checklist": checklist.model_dump()}


# ---------------------------------------------------------------------------
# 5. 그래프 조립 (순차 구조 — 어제 패턴과 동일, 안정성 우선)
# ---------------------------------------------------------------------------

_graph_builder = StateGraph(ConsultState)

_graph_builder.add_node("extract_all_signals", extract_all_signals_node)
_graph_builder.add_node("eligibility_rule", eligibility_rule_node)
_graph_builder.add_node("build_checklist", build_checklist_node)

_graph_builder.add_edge(START, "extract_all_signals")
_graph_builder.add_edge("extract_all_signals", "eligibility_rule")
_graph_builder.add_edge("eligibility_rule", "build_checklist")
_graph_builder.add_edge("build_checklist", END)

eligibility_graph = _graph_builder.compile()
