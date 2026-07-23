# test_verify.py — form_verifier(v2) 단독 동작 확인용
#
# output/에 이미 만들어진 초안 3개를, 각자의 원본 서식과 비교해 검증한다.
# 실행: python test_verify.py  (ai-api 루트에서)

import sys
import json
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from services.form_drafter import find_hwpx
from services.form_verifier import verify

OUTPUT = Path("output")

CASES = [
    {
        "form": "양육비심판청구(과거양육비)",
        "extracted": {
            "청구인": {"이름": "김영희", "관계": "양육자(모)"},
            "상대방": {"이름": "이철수", "관계": "비양육자(부)", "직업": "회사원"},
            "사건본인": {"이름": "이수민", "생년월일": "2015-03-20"},
            "월양육비": 500000, "미지급개월": 6, "미지급총액": 3000000,
            "미지급시작": "2026-01",
        },
    },
    {
        "form": "이혼 및 위자료 조정신청서",
        "extracted": {
            "청구인": {"이름": "박지연", "관계": "처"},
            "상대방": {"이름": "최민호", "관계": "부"},
            "사건본인": {"이름": "최서준", "나이": 8},
            "혼인일": "2016-05-14", "위자료청구액": 30000000,
            "이혼사유": "도박, 폭언",
        },
    },
    {
        "form": "친권 일부제한 심판 청구서",
        "extracted": {
            "청구인": {"이름": "정수진", "관계": "모"},
            "상대방": {"이름": "강태우", "관계": "부(친권자)"},
            "사건본인": {"이름": "강하늘", "생년월일": "2017-09-02"},
            "제한필요권한": "의료행위 동의권",
        },
    },
]


def find_draft(form_stem: str):
    exact = OUTPUT / f"{form_stem}_초안.hwpx"
    if exact.exists():
        return exact
    cands = sorted(OUTPUT.glob(f"{form_stem}_초안*.hwpx"))
    return cands[-1] if cands else None


if __name__ == "__main__":
    for c in CASES:
        print(f"\n{'='*60}\n{c['form']}\n{'='*60}")

        original = find_hwpx(c["form"])
        draft = find_draft(c["form"])

        if original is None:
            print("  [X] 원본 서식을 찾지 못함")
            continue
        if draft is None:
            print("  [X] 초안 파일이 output/에 없음 (먼저 test_flow.py 실행)")
            continue

        print(f"  원본: {original}")
        print(f"  초안: {draft}")

        rep = verify(original, draft, c["extracted"])

        print(f"\n  [자동화 등급] {rep['grade']}")
        print(f"  자리표시자: 원본 {rep['placeholders_original']}개 "
              f"-> 초안 잔존 {rep['placeholders_remaining']}개 "
              f"(PII {rep['placeholders_remaining_pii']} / 기타 {rep['placeholders_remaining_other']})")
        print(f"  반영됨({len(rep['reflected'])}): {rep['reflected']}")
        if rep["not_reflected"]:
            print(f"  [!] 반영안됨: {rep['not_reflected']}")
        if rep["example_residue"]:
            print(f"  [!] 남의사연 잔존(예시문단): {rep['example_residue']}")
        if rep["hallucinated_dates"]:
            print(f"  [!] 환각 의심 날짜: {rep['hallucinated_dates']}")
        if rep["hallucinated_money"]:
            print(f"  [!] 환각 의심 금액: {rep['hallucinated_money']}")

    print("\n\n(참고) 오탐이 있으면 그 목록을 붙여줘 - 기준을 조정한다.")