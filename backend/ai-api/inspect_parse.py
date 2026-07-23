# inspect_paras.py — 원본 서식의 문단 구조를 그대로 출력
# 실행: python inspect_paras.py  (ai-api 루트에서)

import sys
from pathlib import Path
from hwpx import HwpxDocument

sys.stdout.reconfigure(encoding="utf-8")

FORM = "서식_hwpx/친족/이혼 및 위자료/이혼 및 위자료 조정신청서.hwpx"

doc = HwpxDocument.open(FORM)

idx = 0
for sec in doc.sections:
    for p in sec.paragraphs:
        runs = getattr(p, "runs", [])
        text = "".join(getattr(r, "text", "") or "" for r in runs)
        # 자리표시자 포함 여부 표시
        import re
        has_ph = bool(re.search(r"○○|□□|◎◎|20○○|19○○", text))
        mark = " <PH>" if has_ph else ""
        print(f"[{idx}] runs={len(runs)} len={len(text)}{mark}")
        print(f"     {text[:90]}")
        idx += 1

print(f"\n총 {idx}개 문단")