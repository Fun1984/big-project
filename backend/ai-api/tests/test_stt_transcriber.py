import importlib
import os
import sys

import openai
import pytest

import app.ai.stt.transcriber as transcriber


def _write_bytes(path: str, size: int) -> None:
    with open(path, "wb") as f:
        f.write(b"\0" * size)


def test_transcriber_import_does_not_create_openai_client(monkeypatch):
    """다른 OpenAI 호출부와 같은 계약: import 시점에 클라이언트를 만들지 않는다.
    (tests/test_form_drafter.py의 같은 이름 테스트를 이 모듈에도 그대로 적용)"""

    def fail_if_created(*args, **kwargs):
        raise AssertionError("OpenAI client was created during import.")

    monkeypatch.setattr(openai, "OpenAI", fail_if_created)

    sys.modules.pop("app.ai.stt.transcriber", None)
    module = importlib.import_module("app.ai.stt.transcriber")

    assert callable(module.transcribe_file)


class FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

        class _Audio:
            def __init__(self, outer):
                self._outer = outer

            @property
            def transcriptions(self):
                return self

            def create(self, **kwargs):
                self._outer.calls.append(kwargs)
                return self._outer._responses.pop(0)

        self.audio = _Audio(self)


def test_transcribe_file_small_upload_single_call(tmp_path, monkeypatch):
    """25MB 미만이면 압축 1회 + API 1회. model/language가 그대로 전달돼야 한다."""
    source = tmp_path / "input.mp4"
    source.write_bytes(b"fake video bytes")

    def fake_compress(source_path, dest_path):
        _write_bytes(dest_path, 1024)  # 상한보다 훨씬 작다

    fake_client = FakeClient(responses=["안녕하세요 상담 내용입니다"])

    monkeypatch.setattr(transcriber, "_compress", fake_compress)
    monkeypatch.setattr(transcriber, "_client", lambda: fake_client)
    monkeypatch.setattr(transcriber, "STT_API_MODEL", "whisper-1")

    result = transcriber.transcribe_file(str(source))

    assert result == "안녕하세요 상담 내용입니다"
    assert len(fake_client.calls) == 1
    call = fake_client.calls[0]
    assert call["model"] == "whisper-1"
    assert call["language"] == "ko"
    assert call["response_format"] == "text"


def test_transcribe_file_large_upload_splits_and_joins(tmp_path, monkeypatch):
    """상한을 넘으면 조각으로 나눠 각각 호출하고, 결과를 공백으로 이어붙인다."""
    source = tmp_path / "input.mp4"
    source.write_bytes(b"fake video bytes")

    # 상한을 낮게 잡아 "압축해도 큰 파일"을 쉽게 재현한다.
    monkeypatch.setattr(transcriber, "MAX_UPLOAD_BYTES", 100)

    def fake_compress(source_path, dest_path):
        _write_bytes(dest_path, 1000)  # 낮춘 상한(100바이트)보다 크다

    chunk_paths = []

    def fake_split(path, out_dir):
        os.makedirs(out_dir, exist_ok=True)
        for i in range(3):
            chunk_path = os.path.join(out_dir, f"chunk_{i}.mp3")
            _write_bytes(chunk_path, 10)
            chunk_paths.append(chunk_path)
        return chunk_paths

    fake_client = FakeClient(responses=["첫 번째 조각", "두 번째 조각", "세 번째 조각"])

    monkeypatch.setattr(transcriber, "_compress", fake_compress)
    monkeypatch.setattr(transcriber, "_split", fake_split)
    monkeypatch.setattr(transcriber, "_client", lambda: fake_client)

    result = transcriber.transcribe_file(str(source))

    assert result == "첫 번째 조각 두 번째 조각 세 번째 조각"
    assert len(fake_client.calls) == 3


def test_transcribe_file_propagates_ffmpeg_failure(tmp_path, monkeypatch):
    """ffmpeg가 실패하면 빈 문자열로 감추지 않고 그대로 올린다.
    (부르는 쪽이 '말이 없는 녹음'과 구분해야 하므로)"""
    source = tmp_path / "input.mp4"
    source.write_bytes(b"fake video bytes")

    def fake_compress(source_path, dest_path):
        raise RuntimeError("ffmpeg 실패: Invalid data found when processing input")

    monkeypatch.setattr(transcriber, "_compress", fake_compress)

    with pytest.raises(RuntimeError, match="ffmpeg 실패"):
        transcriber.transcribe_file(str(source))


def test_transcribe_file_cleans_up_work_dir(tmp_path, monkeypatch):
    """작업 디렉터리는 성공/실패와 무관하게 정리돼야 한다."""
    source = tmp_path / "input.mp3"
    source.write_bytes(b"fake audio bytes")

    captured_work_dir = {}

    def fake_compress(source_path, dest_path):
        captured_work_dir["path"] = os.path.dirname(dest_path)
        _write_bytes(dest_path, 10)

    monkeypatch.setattr(transcriber, "_compress", fake_compress)
    monkeypatch.setattr(transcriber, "_client", lambda: FakeClient(responses=["ok"]))

    transcriber.transcribe_file(str(source))

    assert not os.path.exists(captured_work_dir["path"])
