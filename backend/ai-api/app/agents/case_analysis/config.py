"""
환경설정 및 공유 클라이언트(S3 등) 모듈.
Colab의 userdata.get(...) 방식을 .env 파일 기반으로 대체했습니다.
"""
import os

from dotenv import load_dotenv

load_dotenv()  # 프로젝트 루트의 .env 파일을 읽어 os.environ에 채움


def _require_env(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        raise RuntimeError(
            f"환경변수 {key}가 설정되지 않았습니다. .env 파일(.env.example 참고)을 확인하세요."
        )
    return value


# --- OpenAI ---
OPENAI_API_KEY = _require_env("OPENAI_API_KEY")

# --- AWS / S3 ---
AWS_REGION = os.environ.get("AWS_REGION", "ap-northeast-2")
S3_BUCKET_NAME = _require_env("S3_BUCKET_NAME")

# --- Whisper ---
WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL_SIZE", "turbo")


def get_s3_client():
    """boto3 S3 클라이언트. AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY는
    boto3가 환경변수에서 자동으로 읽으므로 별도로 넘기지 않습니다."""
    import boto3

    return boto3.client("s3", region_name=AWS_REGION)
