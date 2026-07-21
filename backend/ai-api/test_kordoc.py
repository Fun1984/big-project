# test_kordoc.py
import json
import subprocess
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path

load_dotenv() # 환경변수 로드

client = OpenAI()  # OPENAI_API_KEY 환경변수 사용

BIN = Path("node_modules/.bin")
KORDOC = str(BIN / "kordoc.cmd") if (BIN / "kordoc.cmd").exists() else "kordoc"


# ── kordoc CLI 래퍼 ──
def parse(hwp_path, md_out):
    subprocess.run([KORDOC, hwp_path, "-o", md_out, "--silent"],
                   check=True, encoding="utf-8")


def patch(hwp_path, md_path, out_path):
    r = subprocess.run([KORDOC, "patch", hwp_path, md_path, "-o", out_path],
                       capture_output=True, encoding="utf-8")
    if r.stdout:
        print(r.stdout)
    if r.returncode != 0:
        print(f"⚠️ patch 일부 미반영 (미지원 문단 존재): exit {r.returncode}")
    return r.returncode == 0


def apply_replacements(md_path, replacements):
    """코드가 직접 치환. LLM은 목록만 만들고 실제 수정은 여기서."""
    text = Path(md_path).read_text(encoding="utf-8")
    applied, missed = 0, []
    for r in replacements:
        before = r["before"]
        if before in text:
            text = text.replace(before, r["after"])
            applied += 1
        else:
            missed.append(before)  # GPT가 원문에 없는 문자열을 만든 경우
    Path(md_path).write_text(text, encoding="utf-8")
    return applied, missed


# ── GPT: 치환목록 생성 ──
SYSTEM_PROMPT = """너는 법률 서식의 빈칸을 채우기 위한 치환 목록을 만드는 도구다.

규칙:
1. 서식 원문의 문구는 절대 바꾸지 않는다.
2. 자리표시자만 실제 값으로 치환한다.
3. **추출정보(extracted)에 명시적으로 존재하는 값만 사용한다.
   추출정보에 없는 항목은 추론하거나 임의로 채우지 말고,
   반드시 unfilled에만 넣는다. 특히 날짜, 금액, 주소는
   추출정보에 정확한 값이 없으면 절대 치환하지 않는다.**
4. before는 서식 마크다운에 실제로 존재하는 문자열을 한 글자도
   틀리지 않게 그대로 복사한다. 공백, 마침표, 특수문자 포함.
   추측해서 만들지 않는다.

출력은 JSON만:
{
  "replacements": [{"before": "...", "after": "..."}],
  "unfilled": ["채우지 못한 항목과 이유"]
}"""


def generate_replacements(markdown: str, extracted: dict) -> dict:
    user_msg = f"[서식 마크다운]\n{markdown}\n\n[추출정보]\n{json.dumps(extracted, ensure_ascii=False, indent=2)}"
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    return json.loads(resp.choices[0].message.content)


# ── 실행 ──
INPUT = Path("input")
OUTPUT = Path("output")
OUTPUT.mkdir(exist_ok=True)

# 추출정보 (모든 서식에 공통 시도. 값 없는 건 unfilled로 빠짐)
extracted = {
    "원고": {"이름": "김영희", "주민번호": "850101-2345678"},
    "피고": {"이름": "이철수", "주민번호": "830505-1234567"},
    "혼인일": "2015-03-15",
    "위자료": 30000000,
    "미지급_임대료": 1800000,
    "월_임대료": 600000,
}

# input 폴더의 모든 hwp를 순회
for hwp in sorted(INPUT.glob("*.hwp")):
    print(f"\n{'='*50}\n{hwp.name}\n{'='*50}")
    md = OUTPUT / f"{hwp.stem}.md"
    result_hwp = OUTPUT / f"{hwp.stem}_결과.hwp"
    try:
        # 1. 파싱
        parse(str(hwp), str(md))
        markdown = md.read_text(encoding="utf-8")

        # 2. GPT 치환목록
        result = generate_replacements(markdown, extracted)
        print(f"  GPT 치환: {len(result['replacements'])}건")
        print(f"  미충족: {result['unfilled']}")

        # 3. 치환 적용
        applied, missed = apply_replacements(str(md), result["replacements"])
        print(f"  실제 적용: {applied}건")
        if missed:
            print(f"  ⚠️ GPT가 지어낸 before: {missed}")

        # 4. patch
        ok = patch(str(hwp), str(md), str(result_hwp))
        print(f"  결과: {'✅ patch 성공' if ok else '⚠️ SKIP 발생'}")
    except Exception as e:
        print(f"  ❌ 실패: {e}")