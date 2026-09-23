"""默认模型、批量输出目录与视频场景检测的轻量回归。"""

from __future__ import annotations

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


def main() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        verify_batch(root)
        verify_slides(root)
    verify_service_identity()
    print("默认路由、批量错误状态、服务标识与视频场景检测回归通过")


if __name__ == "__main__":
    main()
