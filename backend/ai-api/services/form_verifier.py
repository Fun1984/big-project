# services/form_verifier.py — 범용 서식 초안 검증 모듈 (v2, 오탐 제거)
#
# v1 문제: "한글 2~4자 다 긁기"로 고유명사를 잡으려다 서식 본문의 평범한
#   법률 단어(친권자·제한·동의 등)까지 환각 의심으로 잡아 오탐 폭발.
#
# v2 설계: 정규식으로 확실히 잡히는 것만 코드로, 못 잡는 건 LLM 심판으로.
#   [코드로 정확히]
#     - 층1 반영: extracted 값이 초안에 들어갔나
#     - 자리표시자 잔존 개수 → 자동화 등급
#     - 숫자/날짜/금액 환각: 초안의 날짜·금액이 extracted에 있는 값인가
#     - 예시 문단 잔존: 원본의 '자리표시자 섞인 서술 문단'이 초안에 통째로 남았나
#   [LLM 심판으로]
#     - 인명/지명 환각, 역할 교차 → llm_judge()

import re
from pathlib import Path
from hwpx import HwpxDocument


PLACEHOLDER_PATTERNS = [
    r"○\s*○[\s○]*", r"□\s*□[\s□]*", r"◎\s*◎", r"[△▽]{2,}",
    r"20○○", r"19○○", r"_{3,}",
]
PLACEHOLDER_RE = re.compile("|".join(PLACEHOLDER_PATTERNS))

# 상담에 원래 없는 정보(주소·전화·주민등록번호 등)는 채울 근거가 없어 정직하게
# 빈칸으로 남는 게 맞다. 이런 자리는 자동화 등급 산정에서 감점 대상이 아니다.
PII_LABEL_RE = re.compile(r"주민등록번호|등록기준지|주\s*소|전\s*화|우편번호|생년월일|☎")


def _placeholder_breakdown(paragraphs: list) -> tuple:
    """(전체, PII류 문단의 자리표시자, 그 외 자리표시자) 개수."""
    total = pii = other = 0
    for para in paragraphs:
        n = len(PLACEHOLDER_RE.findall(para))
        if not n:
            continue
        total += n
        if PII_LABEL_RE.search(para):
            pii += n
        else:
            other += n
    return total, pii, other


def _paragraphs(path) -> list:
    doc = HwpxDocument.open(str(path))
    paras = []
    for sec in doc.sections:
        for p in sec.paragraphs:
            txt = "".join(getattr(r, "text", "") or ""
                          for r in getattr(p, "runs", []))
            if txt.strip():
                paras.append(txt)
    return paras


def _full_text(path) -> str:
    return "".join(_paragraphs(path))


def _flatten_values(extracted: dict) -> list:
    out = []
    def walk(o):
        if isinstance(o, dict):
            for v in o.values(): walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
        elif o is not None:
            out.append(str(o))
    walk(extracted)
    return out


def _dates(text: str) -> set:
    out = set()
    for m in re.finditer(r"((?:19|20)\d\d)(?:[-.\s년]+(\d{1,2}))?(?:[-.\s월]+(\d{1,2}))?", text):
        y, mo, d = m.group(1), m.group(2), m.group(3)
        out.add(y)
        if mo: out.add(f"{y}-{int(mo):02d}")
        if mo and d: out.add(f"{y}-{int(mo):02d}-{int(d):02d}")
    return out


def _money(text: str) -> set:
    out = set()
    for m in re.findall(r"\d[\d,]*\s*천만", text):
        out.add(int(re.sub(r"[^\d]", "", m)) * 10_000_000)
    for m in re.findall(r"\d[\d,]*\s*만", text):
        n = re.sub(r"[^\d]", "", m)
        if n: out.add(int(n) * 10_000)
    for m in re.findall(r"\d[\d,]{5,}", text):
        out.add(int(m.replace(",", "")))
    return out


def _norm_extracted_dates_money(values: list):
    blob = " ".join(values)
    allowed_dates = _dates(blob)
    allowed_money = _money(blob)
    for v in values:
        if v.isdigit() and len(v) >= 5:
            allowed_money.add(int(v))
    return allowed_dates, allowed_money


def verify(original_path, draft_path, extracted: dict) -> dict:
    orig_paras = _paragraphs(original_path)
    orig = "".join(orig_paras)
    draft_paras = _paragraphs(draft_path)
    draft = "".join(draft_paras)
    values = [v.strip() for v in _flatten_values(extracted) if len(v.strip()) >= 2]

    reflected = [v for v in values if v in draft]
    not_reflected = [v for v in values if v not in draft]

    ph_orig_total, ph_orig_pii, ph_orig_other = _placeholder_breakdown(orig_paras)
    ph_draft_total, ph_draft_pii, ph_draft_other = _placeholder_breakdown(draft_paras)

    allowed_dates, allowed_money = _norm_extracted_dates_money(values)
    draft_dates = _dates(draft)
    draft_money = _money(draft)
    orig_dates = _dates(orig)
    orig_money = _money(orig)
    halluc_dates = [d for d in (draft_dates - orig_dates) if d not in allowed_dates]
    halluc_money = [m for m in (draft_money - orig_money) if m not in allowed_money]

    example_residue = []
    for para in orig_paras:
        has_ph = bool(PLACEHOLDER_RE.search(para))
        is_narrative = len(para) >= 40 and para.count(".") + para.count("다") >= 2
        if has_ph and is_narrative:
            core = PLACEHOLDER_RE.sub("", para)[:30]
            if core.strip() and core.strip() in draft:
                example_residue.append(para[:50] + "...")

    # 등급은 'PII류를 제외한' 잔존 자리표시자만으로 판단한다.
    # 주소·전화·주민등록번호는 상담에 없으면 원래 못 채우는 게 정상이므로
    # 감점 대상이 아니다 (있는 정보를 못 채운 것과는 다르다).
    if not not_reflected and ph_draft_other == 0 and not example_residue:
        grade = "완전"
    elif reflected and not example_residue and ph_draft_other <= max(2, ph_orig_other // 3):
        grade = "부분"
    else:
        grade = "불가"

    return {
        "grade": grade,
        "reflected": reflected,
        "not_reflected": not_reflected,
        "placeholders_original": ph_orig_total,
        "placeholders_remaining": ph_draft_total,
        "placeholders_remaining_pii": ph_draft_pii,
        "placeholders_remaining_other": ph_draft_other,
        "hallucinated_dates": halluc_dates,
        "hallucinated_money": halluc_money,
        "example_residue": example_residue,
    }


def llm_judge(draft_path, extracted: dict, summary: str = "") -> dict:
    import json, os
    from openai import OpenAI
    from dotenv import load_dotenv
    load_dotenv()
    client = OpenAI()
    text = _full_text(draft_path)
    prompt = (
        "법률 서식 초안과 그 근거 상담정보다. 아래만 찾아 JSON으로:\n"
        "1) hallucination: 추출정보/요약에 없는 사실(인명·지명·기관·사건)이 "
        "초안에 등장하는 것. 서식 자체의 안내문구·법률용어는 제외.\n"
        "2) role_swap: 당사자가 뒤바뀐 곳(청구인 자리에 상대방 값 등).\n"
        "없으면 빈 배열.\n\n"
        f"[추출정보]\n{json.dumps(extracted, ensure_ascii=False)}\n\n"
        f"[요약]\n{summary}\n\n[초안]\n{text[:6000]}\n\n"
        '출력: {"hallucination": [], "role_swap": []}'
    )
    resp = client.chat.completions.create(
        model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0,
    )
    return json.loads(resp.choices[0].message.content)


if __name__ == "__main__":
    import sys, json
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) >= 3:
        rep = verify(sys.argv[1], sys.argv[2], {"청구인": {"이름": "박지연"}})
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print("사용법: python form_verifier.py <원본.hwpx> <초안.hwpx>")