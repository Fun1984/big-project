"""
로컬 실행용 스마트 테스트 스크립트.
실제 모델이 뽑은 출력을 눈으로 확인하기 위한 용도.

사용법:
    cd backend/ai-api
    python test_run.py
"""

import json
from dotenv import load_dotenv

load_dotenv()  # .env의 OPENAI_API_KEY 로드

from app.services.llm_client import analyze_consultation

# few-shot에 없는 새로운 입력으로 테스트 (모델이 실제로 분류/추출을 하는지 확인하는 게 목적)
TEST_INPUT = "저희 아버지가 유언장을 남기고 돌아가셨는데, 유언장에 저는 한 푼도 없고 동생한테만 전 재산을 준다고 되어있어요. 이거 너무 억울한데 저도 뭔가 받을 방법이 있나요?"

if __name__ == "__main__":
    result = analyze_consultation(TEST_INPUT)
    print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
