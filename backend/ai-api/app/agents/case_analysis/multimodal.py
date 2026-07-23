"""
submitted_file_link(S3 key 배열)에 담긴 파일들을 다운로드하고
STT/문서 텍스트 추출을 수행하는 모듈. Colab notebook의 로직을 그대로 이식.
"""
import os
import re
import tempfile
from urllib.parse import urlparse

from .config import S3_BUCKET_NAME, WHISPER_MODEL_SIZE, get_s3_client

s3 = get_s3_client()

AUDIO_VIDEO_EXTS = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".mp4", ".mov", ".avi", ".webm", ".mkv"}
CAPTION_EXTS = {".vtt", ".srt"}
DOCUMENT_EXTS = {".pdf", ".docx", ".txt", ".md"}
UNSUPPORTED_DOC_EXTS = {".hwp", ".hwpx"}  # kordoc 파이프라인 연동 필요 (이번 백본 범위 밖)

_whisper_model = None


def get_whisper_model():
    """Whisper 모델은 프로세스당 최초 1회만 로드해서 재사용.
    FastAPI에서는 요청마다 호출하지 말고 서버 startup 시점에 한 번 미리 불러둘 것."""
    global _whisper_model
    if _whisper_model is None:
        import whisper

        print(f"[whisper] '{WHISPER_MODEL_SIZE}' 모델 로딩 중... (최초 1회, 다소 시간 소요)")
        _whisper_model = whisper.load_model(WHISPER_MODEL_SIZE)
    return _whisper_model


def determine_file_category(url: str, content_type: str = "") -> str:
    """확장자 우선 판별 -> 실패 시 Content-Type 보조 판별"""
    ext = os.path.splitext(urlparse(url).path)[1].lower()

    if ext in AUDIO_VIDEO_EXTS:
        return "audio_video"
    if ext in CAPTION_EXTS:
        return "caption"
    if ext in DOCUMENT_EXTS:
        return "document"
    if ext in UNSUPPORTED_DOC_EXTS:
        return "unsupported_hwp"

    ct = (content_type or "").lower()
    if ct.startswith("audio/") or ct.startswith("video/"):
        return "audio_video"
    if "vtt" in ct or "srt" in ct or ct.startswith("text/vtt"):
        return "caption"
    if ct == "application/pdf":
        return "document"
    if "wordprocessingml" in ct:  # docx
        return "document"
    if ct.startswith("text/"):
        return "document"

    return "unsupported"


def parse_s3_key(link: str) -> tuple:
    """link가 "s3://bucket/key" 형태면 (bucket, key)로 분리하고,
    그냥 "recording.mp3" 같은 key만 있으면 기본 버킷(S3_BUCKET_NAME)을 사용한다."""
    if link.startswith("s3://"):
        parsed = urlparse(link)
        return parsed.netloc, parsed.path.lstrip("/")
    return S3_BUCKET_NAME, link


def download_to_temp_from_s3(link: str) -> tuple:
    """S3 key(또는 s3:// URI)를 받아 임시 파일로 다운로드. 반환: (로컬경로, content_type)"""
    bucket, key = parse_s3_key(link)
    obj = s3.get_object(Bucket=bucket, Key=key)
    content_type = obj.get("ContentType", "")

    suffix = os.path.splitext(key)[1] or ""
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(obj["Body"].read())

    return tmp_path, content_type


def extract_text_from_audio_video(local_path: str) -> str:
    model = get_whisper_model()
    result = model.transcribe(local_path, language="ko")
    return result.get("text", "").strip()


def extract_text_from_caption(local_path: str) -> str:
    """VTT/SRT의 타임스탬프, 큐 번호, WEBVTT 헤더를 제거하고 텍스트 줄만 추출"""
    with open(local_path, "r", encoding="utf-8", errors="ignore") as f:
        raw = f.read()

    lines = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.upper().startswith("WEBVTT"):
            continue
        if re.match(r"^\d+$", line):  # 큐 번호
            continue
        if "-->" in line:  # 타임스탬프 라인
            continue
        lines.append(line)
    return " ".join(lines).strip()


def extract_text_from_document(local_path: str, ext: str) -> str:
    if ext == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(local_path)
        return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    elif ext == ".docx":
        import docx

        d = docx.Document(local_path)
        return "\n".join(p.text for p in d.paragraphs).strip()
    elif ext in (".txt", ".md"):
        with open(local_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read().strip()
    return ""
