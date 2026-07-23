"""
agents/missing_data/modal.py

누락자료/추가조사 필요항목 감지에 쓰이는 모든 pydantic 스키마, LangGraph State,
FastAPI 요청/응답 모델을 모아둔 모듈.

- 이 노드는 case_type에 상관없이 범용 로직으로 동작한다 (사건유형별 분기 없음).
- candidate_generation 단계는 자유 판단으로 후보를 뽑고, validation 단계가
  confidence 점수를 매겨 최종 채택 여부를 코드 레벨(threshold)에서 결정한다.
  -> 어느 쪽도 "~이다" 식 확정적 법률판단을 내리지 않음 (HITL 원칙 유지).
"""

from typing import TypedDict, List, Literal

from pydantic import BaseModel, Field

from app.agents.rescue_check.modal import (
    LLMSignalBase,
    RawInput,
    CaseAnalysisPayload,
    EligibilityCheckRequest,
    ConsultState,
)


# ---------------------------------------------------------------------------
# 누락 항목 스키마
# ---------------------------------------------------------------------------

MissingItemType = Literal["증빙", "사실관계"]


class MissingItemCandidate(LLMSignalBase):
    """후보 생성(candidate_generation) 단계 출력 - 아직 검증 전"""
    item: str = Field(description="누락된 것으로 보이는 구체적 항목명")
    type: MissingItemType = Field(description="증빙자료 부족인지, 사실관계 미확정인지")
    reason: str = Field(description="왜 이 항목이 필요한지, 어떤 판단/서식 작성에 영향을 주는지")


class MissingItemValidated(MissingItemCandidate):
    """검증(validation) 단계 출력 - 신뢰도 점수 포함"""
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="이 항목이 '실제로 원본 자료에 없다'는 판단에 대한 확신도 (0~1)",
    )
    evidence_check_note: str = Field(
        description="원본 텍스트를 재확인한 근거 요약 (왜 이 confidence를 매겼는지)"
    )


class CandidateList(BaseModel):
    candidates: List[MissingItemCandidate] = Field(default_factory=list)


class ValidatedList(BaseModel):
    validated: List[MissingItemValidated] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# LangGraph State (rescue_check.ConsultState 확장)
# ---------------------------------------------------------------------------

class MissingDataState(ConsultState, total=False):
    # relief_review_checklist 등 어제/오늘 단계 필드는 ConsultState에 이미 포함되어 있음.
    candidate_missing_items: List[dict]
    missing_items: List[dict]  # 최종 산출물 (화면 노출 + 다음 노드 공용)


# ---------------------------------------------------------------------------
# FastAPI 요청/응답 모델
# ---------------------------------------------------------------------------

class MissingDataCheckRequest(BaseModel):
    """/eligibility/analyze 까지의 응답을 그대로 이 스키마로 받아서 넘기는 구조."""
    raw_input: RawInput
    case_analysis: CaseAnalysisPayload
    relief_review_checklist: dict  # /eligibility/analyze 응답의 relief_review_checklist 그대로

    def to_consult_fields(self) -> dict:
        """EligibilityCheckRequest의 텍스트 조합 로직을 그대로 재사용하고,
        여기에 relief_review_checklist만 얹는다 (중복 로직 방지)."""
        base_fields = EligibilityCheckRequest(
            raw_input=self.raw_input,
            case_analysis=self.case_analysis,
        ).to_consult_fields()
        return {**base_fields, "relief_review_checklist": self.relief_review_checklist}


class MissingDataCheckResponse(BaseModel):
    missing_items: List[dict]
