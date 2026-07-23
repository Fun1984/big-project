"""
agents/rescue_check/modal.py

법률구조 대상 여부 판단 + 구조검토 체크리스트(승소가능성/집행가능성/구조타당성)에 쓰이는
모든 pydantic 스키마와 LangGraph State, FastAPI 요청/응답 모델을 모아둔 모듈.

- 구조대상자 여부만 EligibilityRuleResult가 대상/비대상/판단보류라는 결론을 갖는다.
- 승소가능성/집행가능성/구조타당성 스키마(Winnability/Executability/ReliefAppropriateness)는
  의도적으로 결론 필드가 없다 — AI가 판단하지 않고 신호만 추출한다는 걸 스키마로 강제.
"""

from typing import TypedDict, Optional, Literal, List, Union, get_origin, get_args

from pydantic import BaseModel, Field, model_validator
from pydantic_core import PydanticUndefined


# ---------------------------------------------------------------------------
# 공통 베이스
# ---------------------------------------------------------------------------

class LLMSignalBase(BaseModel):
    """LLM 구조화 출력 스키마 공통 베이스: Optional이 아닌 필드에 None -> 기본값 자동 보정.

    method="function_calling" 사용 시 모델이 값을 채우지 못하고 null을 반환하는
    경우가 있어(리스트 필드뿐 아니라 bool 등도 마찬가지), 검증 전(pre-validation)
    단계에서 "이 필드는 원래 None을 허용하지 않는데 None이 왔다"를 감지해
    pydantic에 정의된 기본값(default / default_factory)으로 치환한다.
    """

    @model_validator(mode="before")
    @classmethod
    def _coerce_none_to_default(cls, data):
        if not isinstance(data, dict):
            return data
        for name, field in cls.model_fields.items():
            if name not in data or data.get(name) is not None:
                continue
            annotation = field.annotation
            origin = get_origin(annotation)
            if origin is Union and type(None) in get_args(annotation):
                continue  # Optional[...] 필드는 None이 정상값이므로 그대로 둠
            default = field.get_default(call_default_factory=True)
            if default is not PydanticUndefined:
                data[name] = default
        return data


# ---------------------------------------------------------------------------
# 구조대상자 여부 - 신호 추출용 (판단 아님, Rule Engine 입력용 원자료만)
# ---------------------------------------------------------------------------

class IncomePropertySignal(LLMSignalBase):
    """소득·재산 관련 언급 추출 (판단 아님, 신호만 추출 — 최종 판단은 Rule Engine)"""
    is_basic_livelihood_recipient_mentioned: Optional[bool] = Field(
        None, description="기초생활수급자라는 언급/암시가 상담 내용에 있는지"
    )
    is_near_poverty_class_mentioned: Optional[bool] = Field(
        None, description="차상위계층 언급 여부"
    )
    household_size: Optional[int] = Field(
        None, description="가구원 수. 언급 없으면 null (기준중위소득표 조회에 필요)"
    )
    monthly_income_estimate: Optional[float] = Field(
        None, description="상담 내용에서 추정 가능한 월평균소득(원). 언급 없으면 null"
    )
    is_small_business_context: bool = Field(
        False, description="소상공인 관련 사건 맥락인지 (150% 특례 적용 여부 판단용)"
    )
    income_evidence_mentioned: List[str] = Field(
        default_factory=list,
        description="소득증빙, 가족관계증명, 장애인 증명 등 언급/제공된 자료 목록"
    )
    extraction_confidence: Literal["명시적", "추정", "불명확"] = Field(
        description="위 정보가 상담 내용에 직접 언급됐는지, 정황상 추정인지"
    )


class SpecialStatusSignal(LLMSignalBase):
    """특정 신분 요건 관련 언급 추출"""
    matched_categories: List[Literal[
        "소년소녀가장", "모자가정", "장애인",
        "국내거주 저소득 외국인근로자",
        "법원 소송구조결정 피구조자",
        "국선변호 대상 피의자·피고인", "그 외"
    ]] = Field(default_factory=list)
    category_reasons: List[str] = Field(
        default_factory=list,
        description="카테고리별 판단 근거. '카테고리명: 근거 1문장' 형식 문자열 목록"
    )
    status_evidence_mentioned: List[str] = Field(default_factory=list)
    extraction_confidence: Literal["명시적", "추정", "불명확"]


# ---------------------------------------------------------------------------
# 승소가능성 / 집행가능성 / 구조타당성 - 체크리스트 신호 추출용 (결론 없음)
# ---------------------------------------------------------------------------

class WinnabilitySignal(LLMSignalBase):
    """승소가능성 검토 보조 신호 (참고용 — 최종 판단은 조사담당변호사)"""
    submitted_evidence_types: List[str] = Field(default_factory=list)
    subjective_circumstances_summary: Optional[str] = Field(
        None, description="구조대상자의 주관적 사정 요약 (원문 인용 금지)"
    )
    statute_of_limitations_flag: Optional[Literal["완성 명백", "미완성", "계산 불가"]] = Field(
        None, description="Rule Engine이 계산 후 채워 넣는 필드 (LLM은 기산일만 추출)"
    )
    limitation_start_date: Optional[str] = Field(
        None, description="시효 기산일 (YYYY-MM-DD). 추출 불가하면 null"
    )
    limitation_period_years: Optional[float] = Field(
        None, description="적용 가능 시효기간(년). 명시적 언급/추정 가능하면 채움. 없으면 "
        "사건유형별 기본값(config.STATUTE_OF_LIMITATIONS_MAP)을 Rule Engine이 사용"
    )
    claim_existence_hint: Optional[Literal["청구권 존재 언급", "청구권 부존재 시사", "판단 불가"]] = None
    fact_provability_hint: Optional[Literal["입증 가능 시사", "입증 곤란 시사", "판단 불가"]] = None
    extraction_confidence: Literal["명시적", "추정", "불명확"]
    review_note: str = Field(description="단정 표현 금지. '~로 보임' 형태만 사용")


class ExecutabilitySignal(LLMSignalBase):
    """집행가능성 검토 보조 신호"""
    debtor_asset_status: Optional[Literal["무재산자 언급", "소재불명 언급", "재산 확인 언급", "판단 불가"]] = None
    extraction_confidence: Literal["명시적", "추정", "불명확"]
    review_note: str


class ReliefAppropriatenessSignal(LLMSignalBase):
    """구조타당성 검토 보조 신호"""
    case_nature: Optional[Literal["단순 개인간 이해다툼", "사회적 약자 보호", "판단보류"]] = None
    personal_motive_flags: List[Literal["남소 우려", "감정적 분쟁"]] = Field(default_factory=list)
    alternative_relief_mentioned: Optional[bool] = None
    low_value_claim_mentioned: Optional[bool] = None
    out_of_scope_flags: List[Literal["법인 관련 사건", "종중 관련 사건", "그 외"]] = Field(default_factory=list)
    extraction_confidence: Literal["명시적", "추정", "불명확"]
    review_note: str


# ---------------------------------------------------------------------------
# Rule Engine 산출 스키마 (LLM 미개입, 우리 코드가 직접 채움)
# ---------------------------------------------------------------------------

class EligibilityRuleResult(BaseModel):
    """법률구조법 대상 여부 - Rule Engine 최종 산출 (LLM 미개입, 유일하게 결론을 내는 항목)"""
    income_criterion_met: Optional[bool]
    status_criterion_met: bool
    matched_reasons: List[str]
    required_evidence: List[str]
    evidence_status: Literal["충족", "미비", "확인불가"]
    eligible: Literal["대상", "비대상", "판단보류"]
    applied_income_threshold_ratio: Optional[float] = None
    judgment_note: str = Field(
        description="'~로 보임' 등 참고용 표현. 단정적 법률판단 표현 금지"
    )


class ReliefReviewChecklist(BaseModel):
    """4대 평가기준 통합 체크리스트 (변호사 검토 화면용)"""
    eligibility: EligibilityRuleResult
    winnability: WinnabilitySignal
    executability: ExecutabilitySignal
    appropriateness: ReliefAppropriatenessSignal
    requires_lawyer_review: Literal[True] = True
    checklist_summary_for_lawyer: str


# ---------------------------------------------------------------------------
# LangGraph State (어제 case_analysis 파이프라인의 ConsultState 확장)
# ---------------------------------------------------------------------------

class ConsultState(TypedDict, total=False):
    # --- 어제 단계 (사건유형/긴급도) ---
    summary: str
    details: str
    extracted_content: str
    case_type: str
    case_type_reason: str
    case_emergency_ratio: float
    case_emergency_level: str

    # --- 오늘 단계: 구조대상자 여부 ---
    income_property_signal: dict
    special_status_signal: dict
    eligibility_result: dict

    # --- 오늘 단계: 승소가능성/집행가능성/구조타당성 체크리스트 ---
    winnability_signal: dict
    executability_signal: dict
    appropriateness_signal: dict
    relief_review_checklist: dict


# ---------------------------------------------------------------------------
# FastAPI 요청/응답 모델 (main.py에서 import해서 사용)
# ---------------------------------------------------------------------------

class RawInputContent(BaseModel):
    summary: str
    details: str
    summited_file_link: List[str] = Field(default_factory=list)
    consult_day: Optional[str] = None


class RawInput(BaseModel):
    content: RawInputContent


class ExtractedContentDetail(BaseModel):
    file_link: str
    status: str
    file_type: str
    error: Optional[str] = None


class CaseAnalysisPayload(BaseModel):
    """어제 case_analysis 파이프라인(run_case_analysis)이 만들어내는 case_analysis 블록 그대로."""
    extracted_content: List[str] = Field(default_factory=list)
    extracted_content_detail: List[ExtractedContentDetail] = Field(default_factory=list)
    case_type: str
    case_type_reason: Optional[str] = None
    case_emergency_ratio: Optional[float] = None
    case_emergency_level: Optional[str] = None
    case_emergency_reason: Optional[str] = None


class EligibilityCheckRequest(BaseModel):
    """/case-analysis 응답을 그대로 이 스키마로 다시 받아서 넘기는 구조."""
    raw_input: RawInput
    case_analysis: CaseAnalysisPayload

    def to_consult_fields(self) -> dict:
        """ConsultState 초기값으로 바로 넣을 수 있게 필드 조합.

        extracted_content는 파일별 추출 결과 리스트라서 [0]만 쓰면 안 됨
        (STT 실패로 "내용없음"이 앞쪽에 오면 실제 문서 내용이 통째로 빠짐).
        "내용없음"/빈 문자열은 건너뛰고 나머지를 이어붙임.
        """
        usable_texts = [
            t for t in self.case_analysis.extracted_content
            if t and t.strip() and t.strip() != "내용없음"
        ]
        return {
            "summary": self.raw_input.content.summary,
            "details": self.raw_input.content.details,
            "extracted_content": "\n\n".join(usable_texts),
            "case_type": self.case_analysis.case_type or "",
        }


class EligibilityCheckResponse(BaseModel):
    relief_review_checklist: dict
