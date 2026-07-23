# test_flow.py — 추천 → (선택) → 초안 전체 흐름 테스트
#
# 실제 서비스: 추천 결과를 상담원이 보고 선택 → 초안 생성 (버튼 2개)
# 이 테스트: 1순위를 자동 선택해 흐름을 시뮬레이션
#
# 실행: python test_flow.py  (ai-api 루트에서)

import json
from pathlib import Path

from services.form_recommender import recommend
from services.form_drafter import draft

MOCK_ANALYSES = [
    {
        "id": "mock-양육비-01",
        "case_type": "친족",
        "case_subtype": "양육비",
        "summary": "협의이혼 후 상대방이 매월 50만원 양육비를 올해 1월부터 6개월째 "
                   "미지급. 총 300만원 연체. 상대방은 회사 재직 중인 급여소득자.",
        "extracted_json": {
            "청구인": {"이름": "김영희", "관계": "양육자(모)"},
            "상대방": {"이름": "이철수", "관계": "비양육자(부)", "직업": "회사원"},
            "사건본인": {"이름": "이수민", "생년월일": "2015-03-20"},
            "월양육비": 500000, "미지급개월": 6, "미지급총액": 3000000,
            "미지급시작": "2026-01",
        },
        "missing_info": ["상대방 근무지 상세", "양육비부담조서 유무"],
    },
    {
        "id": "mock-이혼-01",
        "case_type": "친족",
        "case_subtype": "이혼 및 위자료",
        "summary": "혼인 10년차. 배우자의 도박과 지속적 폭언으로 혼인관계 파탄. "
                   "이혼과 함께 위자료 3천만원 청구 희망. 8세 자녀 1명 양육권도 원함.",
        "extracted_json": {
            "청구인": {"이름": "박지연", "관계": "처"},
            "상대방": {"이름": "최민호", "관계": "부"},
            "사건본인": {"이름": "최서준", "나이": 8},
            "혼인일": "2016-05-14", "위자료청구액": 30000000,
            "이혼사유": "도박, 폭언",
        },
        "missing_info": ["재산 내역", "상대방 소득"],
    },
    {
        "id": "mock-친권-01",
        "case_type": "친족",
        "case_subtype": "친권",
        "summary": "이혼 후 친권자인 전 배우자가 자녀 치료(수술)에 동의하지 않아 "
                   "자녀 복리가 위태로움. 의료행위에 관한 친권 일부 제한 필요.",
        "extracted_json": {
            "청구인": {"이름": "정수진", "관계": "모"},
            "상대방": {"이름": "강태우", "관계": "부(친권자)"},
            "사건본인": {"이름": "강하늘", "생년월일": "2017-09-02"},
            "제한필요권한": "의료행위 동의권",
        },
        "missing_info": ["진단서", "수술 필요성 소명자료"],
    },
]


if __name__ == "__main__":
    all_results = []

    for analysis in MOCK_ANALYSES:
        print(f"\n{'='*60}")
        print(f"[{analysis['id']}] {analysis['case_type']} > {analysis['case_subtype']}")
        print('='*60)

        # ── ① 추천 (POST /recommend-forms 에 해당) ──
        rec = recommend(analysis)
        recs = rec.get("recommendations", [])
        print(f"\n① 추천 (후보 {rec.get('candidates_count')}개 중):")
        for r in recs:
            print(f"   {r['rank']}순위: {r['form_name']}")
            print(f"          └ {r['reason']}")
        if not recs:
            print(f"   추천 없음: {rec.get('reason_if_empty')}")
            all_results.append({"id": analysis["id"],
                                "recommended_forms_json": [], "draft": None})
            continue

        # ── ② 선택 (실제로는 상담원이 화면에서 선택. 여기선 1순위 자동) ──
        chosen = recs[0]["form_name"]
        print(f"\n② 선택(시뮬레이션): {chosen}")

        # ── ③ 초안 생성 (POST /generate-draft 에 해당) ──
        d = draft(chosen, analysis["extracted_json"], analysis["summary"])
        if d["error"]:
            print(f"\n③ 초안: ❌ {d['error']}")
        else:
            print(f"\n③ 초안: ✅ {d['file']}")
            print(f"   GPT목록 {d['gpt_count']}건 → 적용 {d['applied']}건")
            if d["missed"]:
                print(f"   ⚠️ 매칭실패: {d['missed'][:3]}")
            if d["unfilled"]:
                print(f"   📋 추가 확인 필요: {d['unfilled'][:3]}")

        all_results.append({
            "id": analysis["id"],
            "recommended_forms_json": recs,
            "chosen": chosen,
            "draft": d,
            "missing_info_json": analysis.get("missing_info", []) + d.get("unfilled", []),
        })

    out = Path("output/추천결과.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n\n전체 결과 저장: {out}")