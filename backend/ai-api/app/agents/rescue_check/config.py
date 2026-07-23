"""
agents/rescue_check/config.py

법률구조 대상 여부 판단(Rule Engine)에 필요한 설정값과 순수 조회 함수만 모아둔 모듈.
pydantic 스키마나 LangGraph 관련 로직은 여기 두지 않음 (그건 modal.py / graph.py 담당).

TODO (팀 확인 필요):
1) MEDIAN_INCOME_TABLE: 2025/2026년은 보건복지부 고시 수치 반영 완료.
   매년 8월 1일 신규 고시 -> 연도 갱신 필요 (계속 늘어나면 DB 테이블로 분리 권장)
2) REQUIRED_EVIDENCE_MAP: "법률검토 기준 분류" 표 F열 기준 초안. 팀 리뷰로 최종 확정 필요
3) STATUTE_OF_LIMITATIONS_MAP: 사건유형별 "보편적" 법정기간만 반영한 기본값.
   실제 사건의 기산일 특칙(상사채권 5년, 근로자 퇴직급여 3년 등)은 반영 안 됨
"""

import os
from datetime import date
from typing import Optional

# ---------------------------------------------------------------------------
# LLM 관련 설정
# ---------------------------------------------------------------------------

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
MODEL_NAME = os.environ.get("KLAC_LLM_MODEL", "gpt-4o-mini")

# 기본값(strict json_schema)은 Optional/List 조합에서
# "'required' must include every key in properties" 류의 400 에러를 낼 수 있어
# function_calling으로 고정.
STRUCTURED_METHOD = "function_calling"


# ---------------------------------------------------------------------------
# 기준중위소득 (소득·재산 기준 판단용)
# ---------------------------------------------------------------------------

# 보건복지부 고시 기준중위소득 (단위: 원/월).
# 출처: 보건복지부 보도자료 "2026년도 기준 중위소득 6.51% 역대 최대로 인상"(2025-07-31 발표)
MEDIAN_INCOME_TABLE: dict[int, dict[int, float]] = {
    2025: {
        1: 2_392_013,
        2: 3_932_658,
        3: 5_025_353,
        4: 6_097_773,
        5: 7_108_192,
        6: 8_064_805,
        7: 8_988_428,
    },
    2026: {
        1: 2_564_238,
        2: 4_199_292,
        3: 5_359_036,
        4: 6_494_738,
        5: 7_556_719,
        6: 8_555_952,
        7: 9_515_150,
    },
}
# 8인 이상: 직전 인원 기준중위소득 + 연도별 증분(2025: 923,623 / 2026: 959,198)
MEDIAN_INCOME_INCREMENT_PER_PERSON = {2025: 923_623, 2026: 959_198}

INCOME_THRESHOLD_RATIO_DEFAULT = 1.25    # 기준중위소득 125% 이하 (일반)
INCOME_THRESHOLD_RATIO_SMALL_BIZ = 1.50  # 기준중위소득 150% 이하 (소상공인 무료법률지원 특례)


# ---------------------------------------------------------------------------
# 필수 소명자료 매핑 (표의 F열 기준 초안 -> 팀 리뷰 필요)
# ---------------------------------------------------------------------------

REQUIRED_EVIDENCE_MAP: dict[str, list[str]] = {
    "기초생활수급자": ["소득증빙", "가족관계증명"],
    "차상위계층": ["소득증빙", "가족관계증명"],
    "월평균소득 기준 이하": ["소득증빙"],
    "소년소녀가장": ["가족관계증명"],
    "모자가정": ["가족관계증명"],
    "장애인": ["장애인 증명"],
    "국내거주 저소득 외국인근로자": ["소득증빙", "그 외"],
    "법원 소송구조결정 피구조자": ["그 외"],
    "국선변호 대상 피의자·피고인": ["그 외"],
}


# ---------------------------------------------------------------------------
# 사건유형별 소멸시효 기본기간(년) — "보편적" 원칙만 반영
# ---------------------------------------------------------------------------

# 임금체불: 근로기준법 제49조(임금채권 3년)
# 불법사금융피해: 민법 제766조1항(안 날로부터 3년, 있은 날로부터 10년은 별도 특칙)
# 개인회생·파산: 시효 개념 비적용(None) -> Rule Engine에서 "계산 불가"로 처리
# 기타: 민법 제162조 일반채권 소멸시효 10년(기본값)
STATUTE_OF_LIMITATIONS_MAP: dict[str, Optional[float]] = {
    "임금체불": 3.0,
    "개인회생": None,
    "개인파산": None,
    "불법사금융피해": 3.0,
    "기타": 10.0,
}


# ---------------------------------------------------------------------------
# 순수 조회 함수 (pydantic/LangGraph 의존 없음)
# ---------------------------------------------------------------------------

def get_median_income(year: int, household_size: int) -> Optional[float]:
    table = MEDIAN_INCOME_TABLE.get(year)
    if table is None:
        return None
    if household_size in table:
        return table[household_size]
    if household_size > 7:
        base = table[7]
        increment = MEDIAN_INCOME_INCREMENT_PER_PERSON.get(year)
        if increment is None:
            return None
        return base + increment * (household_size - 7)
    return None


def get_income_threshold(
    household_size: Optional[int],
    is_small_business: bool = False,
    year: Optional[int] = None,
) -> Optional[float]:
    """가구원수 기준중위소득 * 적용비율(125%/150%). 정보 부족 시 None(판단보류로 이어짐)."""
    if household_size is None:
        return None
    year = year or date.today().year
    median = get_median_income(year, household_size)
    if median is None:
        return None
    ratio = INCOME_THRESHOLD_RATIO_SMALL_BIZ if is_small_business else INCOME_THRESHOLD_RATIO_DEFAULT
    return median * ratio


def map_reasons_to_required_evidence(reasons: list[str]) -> list[str]:
    evidence: set[str] = set()
    for r in reasons:
        evidence.update(REQUIRED_EVIDENCE_MAP.get(r, []))
    return sorted(evidence)
