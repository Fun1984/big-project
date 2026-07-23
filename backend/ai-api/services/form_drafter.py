# services/form_drafter.py — 서식 초안 생성 모듈 (정형 치환 + 예시문단 재서술)
#
# 두 종류의 채우기를 명확히 분리:
#   A. 정형 치환: 자리표시자(○○○ 등) 주변 라벨로 값 치환. GPT가 before/after 생성.
#   B. 예시문단 재서술: 서식에 인쇄된 '남의 사연' 문단을 코드가 인덱스로 특정해,
#      우리 사건 사실로 재서술 후 그 문단 객체만 직접 교체.
#      (텍스트 검색이 아니라 문단 객체 직접 수정 → 오염 불가, run쪼개짐 무관)
#
# 사용:
#   from services.form_drafter import draft
#   result = draft("이혼 및 위자료 조정신청서", extracted, summary)

import json
import re
import time
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from hwpx import HwpxDocument

load_dotenv()
MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
client = OpenAI()

ROOT = Path(__file__).resolve().parent.parent
HWPX_ROOT = ROOT / "서식_hwpx"
OUTPUT = ROOT / "output"
OUTPUT.mkdir(exist_ok=True)

PLACEHOLDER_RE = re.compile(r"○\s*○|□\s*□|◎\s*◎|20○○|19○○|△\s*△")


# ══════════════════════════════════════
# A. 정형 치환용 GPT 프롬프트 (자리표시자 값 채우기만)
# ══════════════════════════════════════
FIELD_PROMPT = """너는 법률 서식의 자리표시자를 실제 값으로 바꾸는 치환목록을 만든다.

규칙:
1. 서식 원문 문구는 바꾸지 않는다. 자리표시자(○○○, ○ ○ ○, □□□, △△△,
   20○○ 등)만 값으로 치환한다.
2. extracted에 명시된 값만 사용. 없으면 unfilled에만 넣는다.
   날짜·금액·주소·주민번호는 정확한 값 없으면 절대 치환하지 않는다.
3. before는 자리표시자 주변 라벨을 포함해 원문에서 유일하게 특정되게 복사
   ("신 청 인   ○  ○  ○" 처럼). 여러 줄에 걸친 긴 서술 문단은 대상 아님
   (그건 별도 처리하므로 여기선 무시).
4. role을 반드시 붙인다: 청구인/상대방/사건본인/기타.
   신청인=청구인, 피신청인=상대방, 원고=청구인, 피고=상대방.
   청구인 자리에 상대방 값을 넣는 것은 최악의 오류다.
5. 같은 사람 이름이 당사자란과 서명란("위 신청인")에 각각 나오면
   각각 별도 항목으로 만든다 (각 위치의 주변 라벨을 before에 포함).

출력 JSON:
{"replacements": [{"before": "...", "after": "...", "role": "청구인"}],
 "unfilled": ["..."]}"""


def _generate_fields(markdown: str, extracted: dict, summary: str) -> dict:
    user_msg = (f"[서식 마크다운]\n{markdown}\n\n"
                f"[사건 요약]\n{summary}\n\n"
                f"[추출정보]\n{json.dumps(extracted, ensure_ascii=False, indent=2)}")
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": FIELD_PROMPT},
                  {"role": "user", "content": user_msg}],
        response_format={"type": "json_object"},
        temperature=0,
    )
    return json.loads(resp.choices[0].message.content)


# ══════════════════════════════════════
# B. 예시문단 재서술
# ══════════════════════════════════════
def _find_example_paragraphs(doc) -> list:
    """예시 사연 문단을 코드가 직접 식별.
    조건: 자리표시자 포함 + 길이 40자↑ + 서술 종결(습니다/였다/입니다 등).
    반환: [(para객체, 실제텍스트), ...] 문서 순서대로."""
    found = []
    for sec in doc.sections:
        for p in sec.paragraphs:
            runs = getattr(p, "runs", [])
            text = "".join(getattr(r, "text", "") or "" for r in runs)
            if len(text) < 40:
                continue
            if not PLACEHOLDER_RE.search(text):
                continue
            # 서술체인지 (종결어미/서술 흔적)
            if re.search(r"(습니다|하였|였다|입니다|되었|하고|근무|생활)", text):
                found.append((p, text))
    return found


REWRITE_PROMPT = """너는 법률 서식의 '예시 사연' 문단을, 실제 사건 사실로 다시 쓰는 도구다.

주어지는 것:
- 원본 예시 문단들 (서식 제작자가 넣은 가상의 사연. 자리표시자 ○○ 등 포함)
- 이번 사건의 요약과 추출정보

할 일:
- 각 원본 문단을 '같은 문체·구조·번호체계(가.나.다. 등)'로 유지하되,
  내용은 이번 사건 사실로 새로 쓴다.

절대 원칙 (매우 중요):
- 원본 예시에 있던 사실(미용실, 구두공장, 사채업자, 경찰서, 특정 날짜·지명·
  인명 등)은 단 하나도 가져오지 않는다. 그건 완전히 다른 남의 사연이다.
- 새 문장에 들어가는 모든 사실(날짜·금액·지명·인명·사건·행위)은 반드시
  요약/추출정보에 존재해야 한다. 없는 사실은 절대 지어내지 않는다.
- 구체적 날짜·금액은 추출정보에 있는 값만. 없으면 그 시점·액수를 언급하지
  않는다. 자리표시자(○○)도 남기지 않는다.
- 당사자는 서식의 역할명(신청인/피신청인)으로 지칭한다.
- 쓸 사실이 부족하면 무리하게 채우지 말고, 있는 사실로 짧게 쓴 뒤 마지막에
  "(구체적 경위는 상담을 통해 보완이 필요합니다.)"로 맺는다.
- 원본 문단 개수만큼 재서술한다. 사실이 정말 없어 못 쓰는 문단은 rewritten을
  빈 문자열 ""로 둔다.

입력 문단은 [0], [1], ... 인덱스로 주어진다.
출력 JSON (입력과 같은 개수, 같은 순서):
{"rewritten": ["새 문단0", "새 문단1", ...]}"""


def _rewrite_examples(example_texts: list, extracted: dict, summary: str) -> list:
    numbered = "\n".join(f"[{i}] {t}" for i, t in enumerate(example_texts))
    user_msg = (f"[원본 예시 문단들]\n{numbered}\n\n"
                f"[사건 요약]\n{summary}\n\n"
                f"[추출정보]\n{json.dumps(extracted, ensure_ascii=False, indent=2)}")
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": REWRITE_PROMPT},
                  {"role": "user", "content": user_msg}],
        response_format={"type": "json_object"},
        temperature=0,
    )
    out = json.loads(resp.choices[0].message.content)
    return out.get("rewritten", [])


# ── 팩트검증: 재서술에 근거 없는 날짜/금액 있으면 위반 ──
def _allowed_facts(extracted, summary):
    blob = summary + " " + json.dumps(extracted, ensure_ascii=False)
    years = set(re.findall(r"(?:19|20)\d\d", blob))
    money = set(re.findall(r"\d{5,}", blob.replace(",", "")))
    return years, money


def _verify_rewrite(text, years, money):
    v = []
    for y in re.findall(r"(?:19|20)\d\d", text):
        if y not in years:
            v.append(f"근거없는연도:{y}")
    for m in re.findall(r"\d{5,}", text.replace(",", "")):
        if m not in money:
            v.append(f"근거없는금액:{m}")
    if PLACEHOLDER_RE.search(text):
        v.append("자리표시자잔존")
    return v


def _set_paragraph_text(p, text: str):
    """문단 객체의 첫 run에 text, 나머지 run 비움."""
    runs = getattr(p, "runs", [])
    if not runs:
        return False
    runs[0].text = text
    for r in runs[1:]:
        r.text = ""
    return True


# ══════════════════════════════════════
# 정형 치환 적용 (계단식)
# ══════════════════════════════════════
def _replace_first_in_runs(doc, target, value):
    for sec in doc.sections:
        for p in sec.paragraphs:
            for run in getattr(p, "runs", []):
                t = getattr(run, "text", None)
                if t and target in t:
                    run.text = t.replace(target, value, 1)
                    return 1
    return 0


def _apply_fields(doc, replacements):
    applied, missed = 0, []
    for r in replacements:
        before, after = r.get("before", ""), r.get("after", "")
        if not before or not after:
            continue
        try:
            n = doc.replace_text_in_runs(before, after)
        except Exception:
            n = 0
        if n and n > 0:
            applied += n
            continue
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
        # run 쪼개짐: 공통 접두·접미 벗겨 핵심만 first-only
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
        missed.append(before[:40])
    return applied, missed


# ══════════════════════════════════════
# 서식 찾기
# ══════════════════════════════════════
def _norm_name(s):
    s = re.sub(r"\s+", "", s)
    for ch in "·,()[]_-":
        s = s.replace(ch, "")
    return s.lower()


def find_hwpx(form_name):
    key = _norm_name(form_name)
    files = list(HWPX_ROOT.rglob("*.hwpx"))
    for f in files:
        if _norm_name(f.stem) == key:
            return f
    for f in files:
        if key in _norm_name(f.stem) or _norm_name(f.stem) in key:
            return f
    return None


def _extract_markdown(doc):
    try:
        return doc.export_rich_markdown()
    except Exception:
        return "\n".join(p.text or "" for sec in doc.sections for p in sec.paragraphs)


# ══════════════════════════════════════
# 메인
# ══════════════════════════════════════
def draft(form_name, extracted, summary=""):
    src = find_hwpx(form_name)
    if src is None:
        return {"file": None, "error": f"서식 파일 없음: {form_name}",
                "applied": 0, "missed": [], "unfilled": [],
                "rewritten_count": 0, "rewrite_rejected": []}

    doc = HwpxDocument.open(str(src))
    md = _extract_markdown(doc)

    # ── A. 정형 치환 ──
    gpt = _generate_fields(md, extracted, summary)
    reps = gpt.get("replacements", [])
    unfilled = gpt.get("unfilled", [])
    applied, missed = _apply_fields(doc, reps)

    # ── B. 예시문단 재서술 ──
    examples = _find_example_paragraphs(doc)   # [(para, text), ...]
    rewritten_count = 0
    rewrite_rejected = []
    if examples:
        texts = [t for (_, t) in examples]
        new_texts = _rewrite_examples(texts, extracted, summary)
        years, money = _allowed_facts(extracted, summary)
        for (para, orig_text), new_text in zip(examples, new_texts):
            if not new_text or not new_text.strip():
                unfilled.append(f"서술문단(근거부족·상담원작성): {orig_text[:25]}")
                continue
            viol = _verify_rewrite(new_text, years, money)
            if viol:
                rewrite_rejected.append({"orig": orig_text[:25], "violations": viol})
                unfilled.append(f"서술문단(검증탈락·상담원작성): {orig_text[:25]}")
                continue
            if _set_paragraph_text(para, new_text):
                rewritten_count += 1

    out = OUTPUT / f"{src.stem}_초안.hwpx"
    try:
        doc.save_to_path(str(out))
    except PermissionError:
        out = OUTPUT / f"{src.stem}_초안_{time.strftime('%H%M%S')}.hwpx"
        doc.save_to_path(str(out))

    return {"file": str(out), "error": None,
            "applied": applied, "missed": missed, "unfilled": unfilled,
            "rewritten_count": rewritten_count, "rewrite_rejected": rewrite_rejected,
            "gpt_count": len(reps)}


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    extracted = {
        "청구인": {"이름": "박지연", "관계": "처"},
        "상대방": {"이름": "최민호", "관계": "부"},
        "사건본인": {"이름": "최서준", "나이": 8},
        "혼인일": "2016-05-14", "위자료청구액": 30000000,
        "이혼사유": "도박, 폭언",
    }
    summary = ("혼인 10년차. 배우자의 도박과 지속적 폭언으로 혼인관계 파탄. "
               "이혼과 함께 위자료 3천만원 청구 희망. 8세 자녀 1명 양육권도 원함.")
    print(json.dumps(draft("이혼 및 위자료 조정신청서", extracted, summary),
                     ensure_ascii=False, indent=2))