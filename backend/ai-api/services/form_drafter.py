# services/form_drafter.py — 서식 초안 생성 모듈
#
# 역할: 서식명 + 추출정보 → 초안 HWPX 생성 (+ 채움/미충족 리포트)
# 사용:
#   from services.form_drafter import draft
#   result = draft("친권 일부제한 심판 청구서", extracted)
#   # {"file": "...", "gpt_count": N, "applied": N, "missed": [...], "unfilled": [...]}
#
# FastAPI 연결 예:
#   POST /generate-draft  → draft(body["form_name"], body["extracted_json"])

import json
import re
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from hwpx import HwpxDocument

load_dotenv()
client = OpenAI()

ROOT = Path(__file__).resolve().parent.parent
HWPX_ROOT = ROOT / "서식_hwpx"     # 변환된 서식 (대분류/소분류/파일.hwpx)
OUTPUT = ROOT / "output"
OUTPUT.mkdir(exist_ok=True)


# ══════════════════════════════════════
# GPT 치환목록 생성
# ══════════════════════════════════════
FILL_PROMPT = """너는 법률 서식의 빈칸을 채우기 위한 치환 목록을 만드는 도구다.

규칙:
1. 서식 원문의 문구는 절대 바꾸지 않는다.
2. 자리표시자(○○○, ○ ○ ○, □□□, 20○○ 등)만 실제 값으로 치환한다.
3. 추출정보(extracted)에 명시적으로 존재하는 값만 사용한다.
   없는 항목은 unfilled에만 넣는다. 날짜·금액·주소는 정확한 값이
   없으면 절대 치환하지 않는다.
4. before는 자리표시자 주변 라벨/문맥을 포함해 원문에서 유일하게
   특정되도록 복사한다. ("청 구 인   ○ ○ ○" 처럼)
4-1. "주소" 같은 라벨이 여러 당사자 아래 반복되면, 문서 흐름상
   어느 당사자 블록인지 판단해 그 당사자의 값만 넣는다.
   라벨 반복 자체는 포기 사유가 아니다. before를 앞뒤 줄까지
   길게 잡으면 특정된다. 청구인 자리에 상대방 값을 넣는 것은
   최악의 오류다. 판단이 안 되는 경우에만 unfilled.
5. after는 before에서 자리표시자만 값으로 바꾼 형태.
5-1. 같은 사람의 이름이 문서 여러 곳(당사자란, 서명란 "위 청구인" 등)
   나오면, 각 위치를 별도 replacement 항목으로 만든다.
   (각각 그 위치의 주변 문맥을 before에 포함)
6. 역할명이 달라도 의미가 대응하면 매핑한다
   (청구인↔신청인↔원고, 상대방↔피신청인↔피고 등).
7. 서술형 기재란 처리:
   [주의: 이 규칙은 추가 작업이다. 규칙 2의 자리표시자 치환을
   먼저 빠짐없이 수행한 뒤, 안내문구 란을 추가로 처리한다.]
   "(청구사유를 구체적으로 기재해 주십시오.)" 같은 안내문구 란은
   summary와 추출정보의 사실만으로 법률 문서 문체의 서술문을
   작성해 치환한다 (before=안내문구 전체, after=작성한 서술문).
   - 추출정보에 없는 사실(날짜, 지명, 병명 등)은 문장에 넣지 않는다.
   - 3~5문장, "~입니다/~습니다" 문체.
   - 마지막 문장은 청구 취지와 연결되게 맺는다.
   대상: "기재해 주십시오", "기재하십시오", "작성해 주세요" 등
   안내문구가 괄호 안에 있는 란.

출력 JSON:
{"replacements": [{"before": "...", "after": "..."}], "unfilled": ["..."]}"""


def _extract_markdown(doc: HwpxDocument) -> str:
    try:
        return doc.export_rich_markdown()
    except Exception:
        return "\n".join(p.text or "" for sec in doc.sections for p in sec.paragraphs)


def _generate_replacements(markdown: str, extracted: dict, summary: str = "") -> dict:
    user_msg = (f"[서식 마크다운]\n{markdown}\n\n"
                f"[사건 요약]\n{summary}\n\n"
                f"[추출정보]\n{json.dumps(extracted, ensure_ascii=False, indent=2)}")
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": FILL_PROMPT},
                  {"role": "user", "content": user_msg}],
        response_format={"type": "json_object"},
        temperature=0,
    )
    return json.loads(resp.choices[0].message.content)


# ══════════════════════════════════════
# 치환 적용 (계단식 매칭)
# ══════════════════════════════════════
def _replace_first_in_runs(doc, target: str, value: str) -> int:
    """문서에서 target이 나오는 첫 run 하나만 치환 (replace-all 방지)."""
    for sec in doc.sections:
        for p in sec.paragraphs:
            for run in getattr(p, "runs", []):
                t = getattr(run, "text", None)
                if t and target in t:
                    run.text = t.replace(target, value, 1)
                    return 1
    return 0


def _apply(doc, replacements: list) -> tuple:
    """계단식 매칭: ①통문자열(replace-all) ②공백변형 ③run쪼개짐 대응(first-only)"""
    applied, missed = 0, []
    for r in replacements:
        before, after = r["before"], r["after"]
        # ① 통 문자열 (라벨 포함이라 all이어도 안전)
        try:
            n = doc.replace_text_in_runs(before, after)
        except Exception:
            n = 0
        if n and n > 0:
            applied += n
            continue
        # ② 공백 변형
        done = False
        for v in {before.replace("   ", " "), before.replace("  ", " "),
                  re.sub(r"\s+", " ", before)}:
            if v == before:
                continue
            try:
                n = doc.replace_text_in_runs(v, after)
            except Exception:
                n = 0
            if n and n > 0:
                applied += n
                done = True
                break
        if done:
            continue
        # ③ run 쪼개짐 대응: before/after 공통 접두·접미를 벗겨
        #    달라지는 핵심만 first-only 치환 (라벨이 떨어져 나가므로 보수적으로)
        i = 0
        while i < min(len(before), len(after)) and before[i] == after[i]:
            i += 1
        j = 0
        while (j < min(len(before), len(after)) - i
               and before[len(before)-1-j] == after[len(after)-1-j]):
            j += 1
        core_b = before[i:len(before)-j] if j else before[i:]
        core_a = after[i:len(after)-j] if j else after[i:]
        if core_b.strip():
            n = _replace_first_in_runs(doc, core_b, core_a)
            if n:
                applied += n
                continue
        missed.append(before)
    return applied, missed


# ══════════════════════════════════════
# 서식 파일 찾기
# ══════════════════════════════════════
def _norm(s: str) -> str:
    s = re.sub(r"\s+", "", s)
    for ch in "·,()[]_-":
        s = s.replace(ch, "")
    return s.lower()


def find_hwpx(form_name: str):
    key = _norm(form_name)
    files = list(HWPX_ROOT.rglob("*.hwpx"))
    for f in files:
        if _norm(f.stem) == key:
            return f
    for f in files:
        if key in _norm(f.stem) or _norm(f.stem) in key:
            return f
    return None


# ══════════════════════════════════════
# 메인: 초안 생성
# ══════════════════════════════════════
def draft(form_name: str, extracted: dict, summary: str = "") -> dict:
    """서식명과 추출정보로 초안 HWPX를 생성한다.

    반환: {"file": 경로 or None, "gpt_count": N, "applied": N,
           "missed": [...], "unfilled": [...], "error": None or str}
    """
    src = find_hwpx(form_name)
    if src is None:
        return {"file": None, "gpt_count": 0, "applied": 0, "missed": [],
                "unfilled": [], "error": f"서식 파일 없음: {form_name}"}

    doc = HwpxDocument.open(str(src))
    md = _extract_markdown(doc)
    gpt = _generate_replacements(md, extracted, summary)
    reps = gpt.get("replacements", [])
    applied, missed = _apply(doc, reps)

    out = OUTPUT / f"{src.stem}_초안.hwpx"
    try:
        doc.save_to_path(str(out))
    except PermissionError:
        out = OUTPUT / f"{src.stem}_초안_{time.strftime('%H%M%S')}.hwpx"
        doc.save_to_path(str(out))

    return {"file": str(out), "gpt_count": len(reps), "applied": applied,
            "missed": missed, "unfilled": gpt.get("unfilled", []), "error": None}


# ── 독립 실행 테스트 ──
if __name__ == "__main__":
    extracted = {
        "청구인": {"이름": "정수진", "관계": "모"},
        "상대방": {"이름": "강태우", "관계": "부(친권자)"},
        "사건본인": {"이름": "강하늘", "생년월일": "2017-09-02"},
        "제한필요권한": "의료행위 동의권",
    }
    summary = ("이혼 후 친권자인 전 배우자가 자녀 치료(수술)에 동의하지 않아 "
               "자녀 복리가 위태로움. 의료행위에 관한 친권 일부 제한 필요.")
    result = draft("친권 일부제한 심판 청구서", extracted, summary)
    print(json.dumps(result, ensure_ascii=False, indent=2))