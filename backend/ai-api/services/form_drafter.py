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
NARRATIVE_END_RE = re.compile(r"(습니다|하였|였다|입니다|되었|하고|근무|생활)")


def _is_narrative(text: str) -> bool:
    return len(text) >= 40 and bool(NARRATIVE_END_RE.search(text))


CLASSIFY_PROMPT = """너는 법률 서식 원문에서 '서식 제작자가 넣은 가상의 예시 사연'을
가려내는 분류기다.

법률 서식에는 보통 두 종류의 긴 문단이 있다:
1. 예시 사연: 실제 있음직한 가상의 인물·사건으로 채워진 완결된 이야기
   (구체적 날짜·금액·직업·장소 등이 이미 다 채워져 있거나, ○○ 같은
   자리표시자가 섞여 있음). 이 사건과 무관한 남의 얘기이며, 상담원이
   실제 사건 내용으로 통째로 바꿔써야 하는 부분이다.
2. 안내문/법조문/정형 문구: 관할법원 안내, 신청취지의 정형 문구, 제출 서류
   설명, "~를 기재해 주십시오" 같은 작성 안내 등 이 사건과 무관하게 항상
   그대로 유지되는 문구.

아래 [문단들]은 문서에서 끊김 없이 이어지는 하나의 블록이다. 이 블록 전체가
1번(예시 사연)인지 2번(안내문 등)인지 판단하라. 조금이라도 애매하면
2번(건드리지 않음)으로 판단한다.

## 출력 JSON
{"is_example": true/false, "reason": "..."}"""


def _classify_is_example(texts: list) -> bool:
    joined = "\n".join(f"[{i}] {t}" for i, t in enumerate(texts))
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "system", "content": CLASSIFY_PROMPT},
                      {"role": "user", "content": f"[문단들]\n{joined}"}],
            response_format={"type": "json_object"},
            temperature=0,
        )
        out = json.loads(resp.choices[0].message.content)
        return bool(out.get("is_example"))
    except Exception:
        return False


def _find_example_paragraphs(doc) -> list:
    """예시 사연 '블록'을 통째로 식별.
    1) 서술체(길이 40자↑ + 종결어미) 문단의 끊김 없는 연속 구간을 블록 후보로 삼는다.
       짧은 문단(제목·안내문, <40자)을 만나면 블록이 끝난다.
    2) 블록에 자리표시자(○○ 등)가 하나라도 있으면 곧바로 예시 블록으로 확정한다.
    3) 자리표시자가 전혀 없는 블록은 GPT로 분류한다 — 서식에는 자리표시자 없이
       완결된 문장으로 인쇄된 가상 사연도 있다(예: 날짜·소득까지 다 채워진
       예시 인물 이야기). 앵커만으로는 이런 블록을 놓친다.
    보수적인 이유: 항상 짧은 문단 경계 안에서만 판단하므로 안내문·법조문을
    건드릴 일이 없고, 애매하면 분류기 자체가 '건드리지 않음'을 기본값으로 한다.
    반환: [(para객체, 실제텍스트), ...] 문서 순서대로."""
    found = []
    for sec in doc.sections:
        paras = list(sec.paragraphs)
        texts = []
        for p in paras:
            runs = getattr(p, "runs", [])
            texts.append("".join(getattr(r, "text", "") or "" for r in runs))
        is_narr = [_is_narrative(t) for t in texts]
        is_blank = [not t.strip() for t in texts]
        has_ph = [is_narr[i] and bool(PLACEHOLDER_RE.search(texts[i]))
                  for i in range(len(paras))]

        i, n = 0, len(paras)
        while i < n:
            if not is_narr[i]:
                i += 1
                continue
            # 서술 문단 사이의 빈 문단(간격용)은 블록을 끊지 않고 건너뛴다.
            # 짧지만 내용 있는 문단(안내문·소제목)만 블록 경계로 취급한다.
            j, last_narr_end = i, i + 1
            while j < n and (is_narr[j] or is_blank[j]):
                if is_narr[j]:
                    last_narr_end = j + 1
                j += 1
            j = last_narr_end
            block_idx = [k for k in range(i, j) if is_narr[k]]
            block_texts = [texts[k] for k in block_idx]
            include = any(has_ph[k] for k in block_idx) or _classify_is_example(block_texts)
            if include:
                for k in block_idx:
                    found.append((paras[k], texts[k]))
            i = j
    return found


REWRITE_PROMPT = """너는 법률 서식의 사실 서술란을, 이번 사건의 상담 내용만으로
작성하는 도구다.

## 무엇을 쓰는가
서식의 특정 서술란(예: "혼인의 파탄" 경위)을, 아래에 주어진 '상담 요약'과
'추출정보'에 담긴 사실만으로 서술한다.

## 절대 원칙 — 근거 있는 서술만 (가장 중요)
1. 문장에 들어가는 모든 사실은 반드시 [상담 요약] 또는 [추출정보]에
   명시적으로 존재해야 한다. 거기 없는 것은 단 한 단어도 쓰지 않는다.
2. 특히 다음을 지어내지 마라 (상담에 없으면 절대 언급 금지):
   - 구체적 행위: 외박, 음주/술, 폭행, 가출, 협박, 고소, 외도 등
     (상담에 "폭언"만 있으면 "폭행"으로 바꾸지 마라. "도박"만 있으면
      "사채·빚·협박" 같은 파생 사실을 덧붙이지 마라.)
   - 구체적 시점·기간·횟수 ("자주", "여러 차례", "매일" 등도 근거 없으면 금지)
   - 직업·경제활동·거주지·제3자
   - 감정·정황 묘사 중 사실을 함의하는 것 ("공포에 떨며" 등)
3. 날짜·금액은 [추출정보]의 값만. 없으면 시점·액수를 언급하지 않는다.
4. 허용되는 것: 상담에 있는 사실을 법률 문체로 다듬고 자연스럽게 잇는 것.
   상담에 있는 사실로부터의 직접적 요약(예: "도박으로 경제적 어려움")은 가능.

## 문체·형식
- 법률 문서 문체("~하였습니다/~입니다"). 당사자는 서식 역할명
  (신청인/피신청인)으로 지칭.
- 서술란은 여러 문단(가. 나. 다. ...)으로 나뉘어 있을 수 있고, 문단 개수가
  주어진다. 있는 사실을 그 개수에 맞춰 자연스럽게 배분한다.
  단, 사실이 적으면 억지로 문단을 채우지 말고 앞 문단들에만 쓰고
  나머지는 빈 문자열로 둔다. (없는 내용으로 칸을 메우지 마라)
- 마지막에 사실이 부족하면 "(구체적 경위는 상담을 통해 보완이 필요합니다.)"로
  한 번만 맺는다.

## 입력
- [서술란 성격]: 이 란이 무슨 내용을 적는 곳인지 (예: 혼인 파탄 경위)
- [문단 개수]: 채워야 할 문단 수 N
- [상담 요약], [추출정보]: 쓸 수 있는 사실의 전부. 이 밖의 것은 없다.
  (원본 예시 문구는 제공하지 않는다. 참고할 남의 사연이 없으니 오직
   상담 사실로만 쓴다.)

## 출력 JSON (문단 N개, 순서대로. 못 채우는 문단은 "")
{"paragraphs": ["문단1", "문단2", ...]}"""


def _infer_field_label(example_texts: list) -> str:
    """예시 문단들이 무슨 란인지 코드가 대략 라벨링 (GPT엔 성격만 전달)."""
    joined = " ".join(example_texts)
    if re.search(r"파탄|혼인|이혼", joined):
        return "혼인의 파탄 경위 (신청인·피신청인 사이 혼인이 파탄에 이른 사정)"
    if re.search(r"양육|미지급|양육비", joined):
        return "양육 및 양육비 관련 경위"
    if re.search(r"친권|양육자|복리", joined):
        return "친권 관련 사정"
    return "사건의 경위 서술"


def _rewrite_examples(example_texts: list, extracted: dict, summary: str) -> list:
    """원본 예시 문구는 GPT에 넘기지 않는다(베낌 방지).
    '무슨 란인지' + '문단 개수' + 우리 사실만 주고 서술하게 한다."""
    n = len(example_texts)
    label = _infer_field_label(example_texts)
    user_msg = (f"[서술란 성격]\n{label}\n\n"
                f"[문단 개수]\n{n}\n\n"
                f"[상담 요약]\n{summary}\n\n"
                f"[추출정보]\n{json.dumps(extracted, ensure_ascii=False, indent=2)}\n\n"
                f"위 사실만으로 문단 {n}개를 작성하라. 사실이 부족하면 뒤 문단은 \"\".")
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": REWRITE_PROMPT},
                  {"role": "user", "content": user_msg}],
        response_format={"type": "json_object"},
        temperature=0,
    )
    out = json.loads(resp.choices[0].message.content)
    paras = out.get("paragraphs", [])
    if len(paras) < n:
        paras = paras + [""] * (n - len(paras))
    return paras[:n]


REVISE_PROMPT = """너는 방금 작성된 법률 서식 문단에서 근거 없는 사실을 골라내는
엄격한 검수자다. 작성 단계에서 "상담에 없는 사실은 쓰지 마라"는 지시가 있었지만,
실제로는 지켜지지 않는 경우가 있다 — 그걸 잡아내는 마지막 관문이 너다.

## 할 일
아래 [작성된 문단]에 있는 모든 구체적 사실(행위·사건·정황·시점·기간·횟수·
장소·직업·제3자·감정묘사 등)을 하나하나 [상담 요약]/[추출정보]와 대조하라.
근거가 없는 부분을 찾으면:
- 그 단어·구·절만 삭제하고 문장이 자연스럽게 이어지도록 다듬는다.
- 문단 전체를 지우지 않는다. 근거 있는 부분은 최대한 살린다.
- 삭제 후 문단이 빈약해져도 억지로 채우지 않는다. 짧으면 짧은 대로 둔다.

특히 아래 유형은 상담/추출정보에 명시적으로 없으면 반드시 삭제한다
(이 목록은 예시일 뿐, 없어도 근거 없는 구체적 사실은 모두 삭제 대상):
외박, 음주/술, 폭행, 협박, 가출, 고소, 외도, 유기, 제3자, 구체적 직업·근무지,
"자주"/"여러 차례"/"매번"처럼 근거 없는 빈도·정도 표현.

이미 근거가 충분한 문단은 그대로 둔다. 없는 사실을 새로 지어내 추가하지 않는다.
빈 문자열("")로 입력된 문단은 그대로 빈 문자열로 둔다.

## 출력 JSON (입력과 같은 개수, 같은 순서)
{"paragraphs": ["...", ...]}"""


def _selfcheck_and_revise(paragraphs: list, extracted: dict, summary: str) -> list:
    """2차 GPT 패스: 1차 작성 결과에서 근거 없는 구체적 사실(행위·정황 등)을
    제거한다. _verify_rewrite는 날짜·금액만 기계적으로 검증하므로,
    '외박했다'류의 서술형 할루시네이션은 이 단계에서만 걸러진다."""
    if not any(p.strip() for p in paragraphs):
        return paragraphs
    numbered = "\n".join(f"[{i}] {p}" for i, p in enumerate(paragraphs))
    user_msg = (f"[작성된 문단]\n{numbered}\n\n"
                f"[상담 요약]\n{summary}\n\n"
                f"[추출정보]\n{json.dumps(extracted, ensure_ascii=False, indent=2)}")
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": REVISE_PROMPT},
                  {"role": "user", "content": user_msg}],
        response_format={"type": "json_object"},
        temperature=0,
    )
    out = json.loads(resp.choices[0].message.content)
    revised = out.get("paragraphs", [])
    if len(revised) != len(paragraphs):
        return paragraphs  # 형식이 깨지면 안전하게 1차 결과 유지 (팩트검증에서 재확인)
    return revised


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
        new_texts = _selfcheck_and_revise(new_texts, extracted, summary)
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