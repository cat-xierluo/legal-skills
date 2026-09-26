"""默认模型、批量输出目录与视频场景检测的轻量回归。

Task-016 整改扩展：
- Task-022：截图阈值单一权威源，CLI 未指定时不携带该字段、显式值仍覆盖
- Task-020：自动 CLI --json 机器模式 stdout 为纯 JSON 且携带认领所需数据；
  claim 命令按标签确定性取向量注册
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch

try:
    import cv2
    import numpy as np
    from fastapi.testclient import TestClient
except ImportError as exc:
    raise SystemExit(
        "缺少回归验证依赖；请先运行 python3 -m pip install "
        "-r assets/requirements.txt -r assets/requirements-moss-mlx.txt"
    ) from exc

import server
import auto_transcribe
import transcribe
import speaker_registry
import slide_extractor
from slide_extractor import SlideExtractor


def verify_service_identity() -> None:
    class HealthResponse(BytesIO):
        status = 200

    for service, expected in (("Local ASR", True), ("unrelated service", False)):
        with patch.object(transcribe.urllib.request, "urlopen", return_value=HealthResponse(
            ('{"service":"' + service + '"}').encode()
        )):
            assert transcribe.check_server("http://127.0.0.1:18765") is expected
        response = Mock(status_code=200)
        response.json.return_value = {"service": service}
        with patch.object(auto_transcribe.requests, "get", return_value=response):
            assert auto_transcribe.check_server("http://127.0.0.1:18765") is expected


def verify_batch(root: Path) -> None:
    source = root / "inputs"
    source.mkdir()
    (source / "conversation.wav").write_bytes(b"synthetic fixture")
    output = root / "new" / "transcripts"
    mock_result = {
        "text": "第一位说话人。",
        "sentence_info": [{"start": 0, "end": 1000, "sentence": "第一位说话人。", "spk": "S01"}],
        "speaker_scope": "global",
    }
    with TestClient(server.app) as client:
        with patch.object(server, "run_transcription", return_value=mock_result):
            response = client.post(
                "/batch_transcribe", json={"directory": str(source), "output_dir": str(output)}
            )
        body = response.json()
        assert response.status_code == 200 and body["success"]
        assert body["results"][0]["resolved_model"] == "moss-mlx"
        assert (output / "conversation.md").is_file()

        with patch.object(server, "run_transcription", side_effect=RuntimeError("test failure")):
            response = client.post(
                "/batch_transcribe", json={"directory": str(source), "output_dir": str(output)}
            )
        body = response.json()
        assert response.status_code == 200 and not body["success"]
        assert body["results"][0]["error"] == "test failure"

    assert server.resolve_requested_model(None) == "moss-mlx"
    assert server.resolve_requested_model("paraformer") == "paraformer"
    assert server.resolve_requested_model("paraformer-onnx") == "paraformer-onnx"


def verify_slides(root: Path) -> None:
    video = root / "slides.mp4"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (640, 360))
    assert writer.isOpened()
    for number in (1, 2, 3):
        for _ in range(40):
            frame = np.full((360, 640, 3), 255, np.uint8)
            cv2.putText(
                frame, f"SLIDE {number}", (70, 190), cv2.FONT_HERSHEY_SIMPLEX,
                2.4, (25 * number, 40 * number, 50 * number), 5,
            )
            cv2.rectangle(frame, (80 * number, 40), (80 * number + 90, 100), (0, 0, 255), -1)
            writer.write(frame)
    writer.release()
    frames = SlideExtractor().extract(str(video), str(root / "frames"))
    assert [frame.timestamp_ms for frame in frames] == [0, 4000, 8000]
    assert all(Path(frame.image_path).is_file() for frame in frames)


def _fake_http_response(body: bytes):
    response = BytesIO(body)
    response.status = 200
    return response


def verify_slide_threshold_consistency(root: Path) -> None:
    """Task-022：单一权威源；CLI 未指定不带字段，显式值覆盖。"""
    assert slide_extractor.DEFAULT_SLIDE_THRESHOLD == 20.0
    assert SlideExtractor().threshold == 20.0
    fields = getattr(server.TranscribeRequest, "model_fields", None) or server.TranscribeRequest.__fields__
    assert fields["slide_threshold"].default is None

    sample = root / "threshold-check.wav"
    sample.write_bytes(b"fixture")
    source = str(sample)
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        raise OSError("stop before network")

    with patch.object(transcribe.urllib.request, "urlopen", side_effect=fake_urlopen):
        transcribe.transcribe_file(source, include_summary_prompt=False)
        assert "slide_threshold" not in captured["payload"], captured["payload"]
        assert "extract_slides" not in captured["payload"]
        transcribe.transcribe_file(source, slide_threshold=27.0, extract_slides=False)
        assert captured["payload"]["slide_threshold"] == 27.0
        assert captured["payload"]["extract_slides"] is False

    captured.clear()
    with patch.object(auto_transcribe.requests, "post", side_effect=_fake_post_capture(captured)):
        try:
            auto_transcribe.transcribe(source, include_summary_prompt=False)
        except OSError:
            pass
        assert "slide_threshold" not in captured["payload"], captured["payload"]
        try:
            auto_transcribe.transcribe(source, slide_threshold=20.0, extract_slides=True)
        except OSError:
            pass
        assert captured["payload"]["slide_threshold"] == 20.0
        assert captured["payload"]["extract_slides"] is True
    print("Task-022 截图阈值：默认单一权威源 20.0，CLI 未指定不覆盖，显式值保留")


def _fake_post_capture(captured: dict):
    def _post(url, json=None, timeout=None, **kwargs):
        captured["payload"] = json
        raise OSError("stop before network")

    return _post


def verify_auto_cli_json(root: Path) -> None:
    """Task-020：--json stdout 为可直接解析的完整响应；认领提示与 claim 命令可用。"""
    sample = root / "audio.wav"
    sample.write_bytes(b"fixture")
    mock_result = {
        "success": True,
        "output_path": str(root / "audio.md"),
        "summary_prompt": "总结提示词",
        "speaker_identification": {"S01": {"name": "杨卫薪", "score": 0.9}, "S02": None},
        "speaker_states": {
            "S01": {"status": "matched", "name": "杨卫薪"},
            "S02": {"status": "unknown", "name": None, "detail": "有声纹向量但未达阈值，可经用户确认后认领注册"},
        },
        "speaker_embeddings": {"S01": [0.0] * 191 + [1.0], "S02": [1.0] + [0.0] * 191},
        "segments": [
            {"start": 0.0, "end": 4.0, "speaker": "S01", "text": "第一人发言"},
            {"start": 4.0, "end": 8.0, "speaker": "S02", "text": "第二人发言"},
        ],
    }
    argv = ["auto_transcribe.py", str(sample), "--json"]
    with patch.object(auto_transcribe, "check_server", return_value=True), \
         patch.object(auto_transcribe, "transcribe", return_value=mock_result), \
         patch.object(sys, "argv", argv):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            auto_transcribe.main()
    parsed = json.loads(stdout.getvalue())  # stdout 必须整体可被标准 JSON 解析器读取
    for key in ("speaker_identification", "speaker_embeddings", "segments", "speaker_states"):
        assert key in parsed and parsed[key] == mock_result[key], key
    # stdout 不含人类模式的认领提示行（响应数据中的"认领"字样除外）
    assert "speaker_registry.py claim" not in stdout.getvalue()
    assert "👥" not in stdout.getvalue()

    # 人类模式：无向量倾倒，有认领提示
    argv = ["auto_transcribe.py", str(sample), "--no-summary"]
    with patch.object(auto_transcribe, "check_server", return_value=True), \
         patch.object(auto_transcribe, "transcribe", return_value=mock_result), \
         patch.object(sys, "argv", argv):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            auto_transcribe.main()
    human_out = stdout.getvalue()
    assert "S02" in human_out and "认领" in human_out
    # 默认不倾倒向量：结构键名与 192 维数组都不出现在人类输出中
    assert "speaker_embeddings" not in human_out
    assert json.dumps(mock_result["speaker_embeddings"]["S01"]) not in human_out

    # --json 与 --prompt-only 互斥
    argv = ["auto_transcribe.py", str(sample), "--json", "--prompt-only"]
    with patch.object(sys, "argv", argv):
        try:
            auto_transcribe.main()
        except SystemExit as exc:
            assert exc.code == 2
        else:
            raise AssertionError("--json 与 --prompt-only 应互斥")

    # claim 命令：从结果 JSON 确定性取向量并注册
    result_file = root / "result.json"
    result_file.write_text(json.dumps(mock_result, ensure_ascii=False), encoding="utf-8")
    registered = {}

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"success": True, "name": "新说话人", "replaced": False, "total": 3}).encode()

    def fake_urlopen(request, timeout=None):
        registered["payload"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse()

    argv = ["speaker_registry.py", "claim", "新说话人", "--result", str(result_file), "--label", "S02"]
    with patch.object(speaker_registry.urllib.request, "urlopen", side_effect=fake_urlopen), \
         patch.object(sys, "argv", argv):
        assert speaker_registry.main() == 0
    assert registered["payload"]["embedding"] == mock_result["speaker_embeddings"]["S02"]
    assert registered["payload"]["source_label"] == "S02"

    # 无该标签 → 非零退出
    argv = ["speaker_registry.py", "claim", "新说话人", "--result", str(result_file), "--label", "S09"]
    with patch.object(sys, "argv", argv):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            assert speaker_registry.main() == 1
    print("Task-020 自动 CLI：--json 纯 JSON 交付、认领提示、claim 确定性取向量全部通过")


def main() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        verify_batch(root)
        verify_slides(root)
        verify_auto_cli_json(root)
        verify_slide_threshold_consistency(root)
    verify_service_identity()
    print("默认路由、批量错误状态、服务标识、视频场景检测、截图阈值一致性与自动 CLI JSON 回归通过")


if __name__ == "__main__":
    main()
