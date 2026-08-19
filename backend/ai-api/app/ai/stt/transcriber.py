"""음성/영상 파일 -> 텍스트. OpenAI 전사 API를 부른다.

왜 API인가 —
예전에는 이 프로세스가 openai-whisper를 직접 돌렸다. 그런데 EC2(t3.xlarge)에 GPU가
없어서 CPU 전용 torch 휠에 가장 작은 축인 'base' 모델로 돌고 있었다. 10분짜리 녹음
하나가 10분 넘게 이 서버의 CPU를 붙들었고(core-api의 read timeout이 20분인 이유다),
그러면서 정확도는 whisper 계열에서 제일 낮았다. 전사를 API로 넘기면 CPU가 풀리고
정확도는 오히려 올라간다.

크기 제한 —
전사 API는 파일 하나에 25MB까지만 받는다. 로컬 whisper에는 없던 제약이고, 첨부는
.mp4/.mov/.avi/.mkv 영상까지 받으므로(multimodal.AUDIO_VIDEO_EXTS) 그냥 올리면 긴
녹화는 전부 실패한다. 그래서 올리기 전에 ffmpeg로 한 번 줄이고, 그래도 넘으면
시간 단위로 쪼개서 각각 전사한 뒤 이어붙인다. 바깥에서 보면 예전과 같이
"경로를 주면 텍스트가 나온다"이다.
"""

import os
import shutil
import subprocess
import tempfile
from functools import lru_cache

from app.ai.config import STT_API_MODEL

# API가 받는 상한은 25MB다. 압축 결과가 예상보다 큰 경우에 대비해 조금 낮춰 잡는다 —
# 경계에서 되돌아오는 413은 조각 하나가 아니라 파일 전체를 실패시킨다.
MAX_UPLOAD_BYTES = 24 * 1024 * 1024

# 16kHz 모노 32kbps. whisper 계열은 내부적으로 어차피 16kHz 모노로 리샘플하므로
# 모델이 실제로 쓰는 정보는 여기서 버려지지 않는다. 대략 240KB/분이라
# 24MB면 100분쯤 들어간다 - 상담 녹음은 이 한 번으로 거의 다 해결된다.
TARGET_SAMPLE_RATE = 16000
TARGET_BITRATE = "32k"

# 조각이 상한에 딱 붙지 않게 여유를 둔다. mp3는 구간마다 압축률이 달라서
# "24MB / 초당바이트"로 계산한 길이가 그대로 24MB가 되지는 않는다.
SEGMENT_SAFETY_RATIO = 0.9

# 업로드 + 전사를 합친 시간이다. 조각 하나(최대 100분 분량)를 기준으로 잡는다.
REQUEST_TIMEOUT_SEC = 600.0


@lru_cache(maxsize=1)
def _client():
    # import 시점에 클라이언트를 만들지 않는다. 이 레포의 다른 OpenAI 호출부와
    # 같은 형태다(app/ai/statutes/explainer.py). 테스트가 이 계약을 강제한다.
    from openai import OpenAI

    return OpenAI(timeout=REQUEST_TIMEOUT_SEC, max_retries=2)


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    """ffmpeg/ffprobe 실행. 인자는 항상 리스트로 넘긴다.

    입력 경로가 S3 key에서 만들어진 임시 파일이라 shell=True를 쓰면
    파일명이 명령줄로 해석될 자리가 생긴다.
    """
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # stderr 마지막 줄이 대개 실제 원인이다. 전체를 실으면 배너까지 딸려온다.
        tail = (result.stderr or "").strip().splitlines()
        reason = tail[-1] if tail else f"exit code {result.returncode}"
        raise RuntimeError(f"{os.path.basename(cmd[0])} 실패: {reason}")
    return result


def _compress(source_path: str, dest_path: str) -> None:
    """영상 트랙을 버리고 16kHz 모노 mp3로 줄인다."""
    _run([
        "ffmpeg", "-nostdin", "-y",
        "-i", source_path,
        "-vn",                          # 영상 트랙 제거 - 전사에 쓰이지 않는다
        "-ac", "1",                     # 모노
        "-ar", str(TARGET_SAMPLE_RATE),
        "-b:a", TARGET_BITRATE,
        dest_path,
    ])


def _duration_sec(path: str) -> float:
    result = _run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path,
    ])
    raw = (result.stdout or "").strip()
    try:
        return float(raw)
    except ValueError as e:
        raise RuntimeError(f"재생 길이를 읽지 못했습니다: {raw!r}") from e


def _split(path: str, out_dir: str) -> list[str]:
    """상한을 넘는 파일을 상한 아래 조각들로 쪼갠다.

    실제 크기와 재생 길이로 초당 바이트를 구해 자를 길이를 정한다.
    비트레이트를 고정값으로 가정하지 않는 이유는, 이 함수가 압축을 건너뛴
    파일에도 쓰일 수 있어서다.
    """
    total_bytes = os.path.getsize(path)
    duration = _duration_sec(path)
    if duration <= 0:
        raise RuntimeError("재생 길이가 0인 파일은 쪼갤 수 없습니다.")

    bytes_per_sec = total_bytes / duration
    segment_sec = max(1, int(MAX_UPLOAD_BYTES * SEGMENT_SAFETY_RATIO / bytes_per_sec))

    ext = os.path.splitext(path)[1] or ".mp3"
    pattern = os.path.join(out_dir, f"chunk_%04d{ext}")
    _run([
        "ffmpeg", "-nostdin", "-y",
        "-i", path,
        "-f", "segment",
        "-segment_time", str(segment_sec),
        "-c", "copy",                   # 이미 목표 포맷이므로 재인코딩하지 않는다
        pattern,
    ])

    chunks = sorted(
        os.path.join(out_dir, name)
        for name in os.listdir(out_dir)
        if name.startswith("chunk_")
    )
    if not chunks:
        raise RuntimeError("파일을 조각으로 나누지 못했습니다.")
    return chunks


def _transcribe_one(path: str) -> str:
    with open(path, "rb") as f:
        text = _client().audio.transcriptions.create(
            model=STT_API_MODEL,
            file=f,
            language="ko",
            response_format="text",
        )
    # response_format="text"면 SDK가 문자열을 그대로 돌려준다. 다만 모델에 따라
    # 객체가 오는 경우가 있어 .text가 있으면 그쪽을 쓴다.
    if not isinstance(text, str):
        text = getattr(text, "text", "") or ""
    return text.strip()


def transcribe_file(local_path: str) -> str:
    """로컬 오디오/영상 파일을 한국어로 전사한다.

    예외는 삼키지 않는다. 부르는 쪽이 이미 각자의 방식으로 처리한다 -
    app/ai/stt/extract.py는 파일 하나의 실패가 전체를 막지 않게 잡고,
    app/routers/stt.py는 사유를 붙여 500으로 바꾼다. 여기서 빈 문자열을
    돌려주면 "말이 없는 녹음"과 구분되지 않는다.
    """
    work_dir = tempfile.mkdtemp(prefix="stt_")
    try:
        compressed = os.path.join(work_dir, "audio.mp3")
        _compress(local_path, compressed)

        if os.path.getsize(compressed) <= MAX_UPLOAD_BYTES:
            return _transcribe_one(compressed)

        chunk_dir = os.path.join(work_dir, "chunks")
        os.makedirs(chunk_dir, exist_ok=True)
        texts = [_transcribe_one(chunk) for chunk in _split(compressed, chunk_dir)]
        # 조각 경계는 문장 중간일 수 있다. 공백으로 잇는 것이 원문에 가장 가깝다.
        return " ".join(t for t in texts if t).strip()
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
