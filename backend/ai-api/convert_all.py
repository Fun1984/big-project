# convert_all_hwpx.py — 서식 전체를 폴더 구조 유지하며 HWPX로 일괄 변환
#
# 준비:
#   1. 서식_친족_상속_가사소송_가족관계등록.zip 을 풀어서
#      backend/ai-api/서식/ 폴더에 넣기 (친족/, 상속/, ... 구조 그대로)
#   2. pip install pyhwpx  (이미 설치됨)
#   3. 한글(한컴오피스) 설치된 PC에서 실행
#
# 실행:  python convert_all_hwpx.py
# 결과:  서식_hwpx/ 폴더에 같은 구조로 .hwpx 생성 + 변환결과 리포트

from pathlib import Path
from pyhwpx import Hwp
import json

SRC = Path("서식")          # 원본 hwp (대분류/소분류 폴더 구조)
DST = Path("서식_hwpx")     # 변환 결과

def is_real_hwpx(path: Path) -> bool:
    """ZIP 시그니처(504b)인지 확인 — 진짜 HWPX 검증"""
    try:
        return path.read_bytes()[:4] == b"PK\x03\x04"
    except Exception:
        return False

def main():
    files = sorted(SRC.rglob("*.hwp"))
    print(f"대상: {len(files)}개")

    hwp = Hwp(visible=False)
    ok, fail = [], []

    try:
        for i, f in enumerate(files, 1):
            rel = f.relative_to(SRC)
            out = DST / rel.with_suffix(".hwpx")
            out.parent.mkdir(parents=True, exist_ok=True)

            # 이미 변환돼 있으면 건너뜀 (중단 후 재실행 가능)
            if out.exists() and is_real_hwpx(out):
                ok.append(str(rel))
                continue

            try:
                hwp.open(str(f.resolve()))
                hwp.save_as(str(out.resolve()), format="HWPX")
                if is_real_hwpx(out):
                    ok.append(str(rel))
                    print(f"[{i}/{len(files)}] ✅ {rel}")
                else:
                    fail.append({"파일": str(rel), "이유": "저장됐지만 HWPX 아님"})
                    print(f"[{i}/{len(files)}] ⚠️ 형식 이상: {rel}")
            except Exception as e:
                fail.append({"파일": str(rel), "이유": str(e)[:200]})
                print(f"[{i}/{len(files)}] ❌ {rel}: {e}")
    finally:
        try:
            hwp.quit()
        except Exception:
            pass

    # 리포트
    print(f"\n{'='*50}")
    print(f"성공: {len(ok)} / 실패: {len(fail)} / 전체: {len(files)}")
    if fail:
        print("\n실패 목록:")
        for x in fail[:20]:
            print(f"  {x['파일']}: {x['이유']}")
    Path("변환결과.json").write_text(
        json.dumps({"성공": len(ok), "실패목록": fail}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print("\n상세: 변환결과.json")

if __name__ == "__main__":
    main()