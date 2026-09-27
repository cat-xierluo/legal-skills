"""默认模型、批量输出目录与视频场景检测的轻量回归。

Task-016 整改扩展：
- Task-022：截图阈值单一权威源，CLI 未指定时不携带该字段、显式值仍覆盖；
  端到端补单文件 HTTP / 两个实际 CLI 对同一视频的截图一致证据（ASR 为 stub，
  HTTP/CLI/FFmpeg/图片链路真实执行）；批量不提取截图、纯音频默认不提取的边界断言
- Task-020：自动 CLI --json 机器模式 stdout 为纯 JSON 且携带认领所需数据；
  claim 命令按标签确定性取向量注册；结果文件新建与覆盖均为 0600（F2）
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
import wave
import socket
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch

try:
    import cv2
    import numpy as np
    import requests
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
        "speaker_identification": {"S01": {"name": "杨律师", "score": 0.9}, "S02": None},
        "speaker_states": {
            "S01": {"status": "matched", "name": "杨律师"},
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


def verify_result_file_permissions(root: Path) -> None:
    """Task-020 F2：结果文件新建与覆盖都保持 0600；覆盖宽权限文件同样收紧。"""
    sample = root / "perm.wav"
    sample.write_bytes(b"fixture")
    payload = {
        "success": True,
        "output_path": str(root / "perm.md"),
        "speaker_embeddings": {"S01": [0.1] * 192},
        "segments": [{"start": 0.0, "end": 2.0, "speaker": "S01", "text": "内容"}],
    }

    # 单元级：目标不存在 / 已有 0600 / 0640 / 0644 四种初态，写后仅本人可读写
    for mode in (None, 0o600, 0o640, 0o644):
        target = root / f"perm-unit-{mode}.json"
        if mode is not None:
            target.write_text("旧内容", encoding="utf-8")
            os.chmod(target, mode)
        saved = auto_transcribe.save_result_file(payload, str(target))
        assert Path(saved) == target
        assert stat.S_IMODE(target.stat().st_mode) & 0o077 == 0, f"初态 {oct(mode or 0)} 写后仍宽权限"
        assert json.loads(target.read_text(encoding="utf-8")) == payload, "文件内容必须等于响应"

    # CLI 级：--save-result 与 --json --save-result 走实际 main()，覆盖 0644 初态
    for extra, label in (([], "human"), (["--json"], "json")):
        target = root / f"perm-cli-{label}.json"
        target.write_text("旧内容", encoding="utf-8")
        os.chmod(target, 0o644)
        argv = ["auto_transcribe.py", str(sample), "--no-summary", "--save-result", str(target)] + extra
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(auto_transcribe, "check_server", return_value=True), \
             patch.object(auto_transcribe, "transcribe", return_value=payload), \
             patch.object(sys, "argv", argv), \
             contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            auto_transcribe.main()
        assert stat.S_IMODE(target.stat().st_mode) & 0o077 == 0, f"{label} 模式覆盖后未收紧权限"
        assert json.loads(target.read_text(encoding="utf-8")) == payload
        if extra:
            json.loads(stdout.getvalue()), "--json 模式 stdout 必须整体可解析"

    # 写入失败：非零退出、不虚报保存成功、旧文件完整、临时文件被清理
    target = root / "perm-fail.json"
    target.write_text("旧内容", encoding="utf-8")
    os.chmod(target, 0o644)
    before = target.read_bytes()
    argv = ["auto_transcribe.py", str(sample), "--no-summary", "--json",
            "--save-result", str(target)]
    with patch.object(auto_transcribe, "check_server", return_value=True), \
         patch.object(auto_transcribe, "transcribe", return_value=payload), \
         patch.object(auto_transcribe.os, "replace", side_effect=OSError("注入的替换失败")), \
         patch.object(sys, "argv", argv), \
         contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        try:
            auto_transcribe.main()
        except SystemExit as exc:
            assert exc.code == 1, "保存失败必须非零退出"
        else:
            raise AssertionError("保存失败必须非零退出")
    assert target.read_bytes() == before, "替换失败时旧文件必须保持完整"
    assert not list(root.glob(".perm-fail.json*")), "失败的临时文件必须被清理"
    print("Task-020 结果文件权限：不存在/0600/0640/0644 四种初态写后均 0600，"
          "CLI 两模式覆盖收紧，替换失败旧文件完整且临时文件清理")


def _write_tone_wav(path: Path, seconds: float, freq: int = 440) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        frames = (np.sin(np.arange(int(16000 * seconds)) * 2 * np.pi * freq / 16000) * 4000).astype("<i2")
        wav.writeframes(frames.tobytes())


def _make_slides_video_with_audio(root: Path, name: str = "lecture.mp4") -> Path:
    """12 秒三页合成视频 + 440Hz 音轨（ffmpeg 合并），供端到端截图链路使用。"""
    silent = root / "slides-silent.mp4"
    writer = cv2.VideoWriter(str(silent), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (640, 360))
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
    audio = root / "lecture.wav"
    _write_tone_wav(audio, 12.0)
    video = root / name
    process = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(silent), "-i", str(audio),
         "-c:v", "copy", "-c:a", "aac", "-shortest", str(video)],
        capture_output=True, text=True,
    )
    assert process.returncode == 0, process.stderr
    return video


_STUB_SERVER_TEMPLATE = '''"""Task-022 端到端用 stub 服务：真实 HTTP/截图链路，MOSS/CAM++ 为同构替身。"""
import sys
import wave
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, "__SCRIPTS_DIR__")
import server
import moss_mlx

# 隔离：声纹库指向临时路径，绝不触碰生产 assets/speaker-profiles.json
server.SPEAKER_PROFILES_PATH = Path("__PROFILES__")


class FakeMoss:
    """按实际 chunk 时长生成三段时间戳（超出真实时长会被产品校验拒绝）。"""

    def generate(self, path, **kwargs):
        with wave.open(path, "rb") as stream:
            duration = stream.getnframes() / stream.getframerate()
        lines = [("S01", "介绍第一页内容。"), ("S02", "这是第二页材料。"), ("S01", "总结第三页要点。")]
        step = duration / len(lines)
        parts = []
        for index, (speaker, text) in enumerate(lines):
            start = index * step
            end = duration if index == len(lines) - 1 else (index + 1) * step
            parts.append(f"[{start:.2f}][{speaker}]{text}[{end:.2f}]")
        return SimpleNamespace(text="".join(parts), generation_tokens=64)


moss_mlx.load_model = lambda *a, **k: FakeMoss()
moss_mlx._speaker_embeddings = lambda *a, **k: {}

import uvicorn

uvicorn.run(server.app, host="127.0.0.1", port=__PORT__, log_level="warning")
'''


def _slide_refs(md_path: Path) -> list[str]:
    return re.findall(r"!\[\]\(([^)]+)\)", md_path.read_text(encoding="utf-8"))


def verify_slides_end_to_end(root: Path) -> None:
    """Task-022：单文件 HTTP / transcribe.py / auto_transcribe.py 对同一视频的
    截图输出一致；显式阈值差异、关闭截图、批量边界、纯音频默认不提取均有断言。
    ASR/CAM++ 用 stub server 替身；HTTP、CLI、FFmpeg、图片文件链路全部真实执行。
    """
    video = _make_slides_video_with_audio(root)
    # 动态选空闲端口，避免历史 stub 残留进程占用固定端口造成假就绪
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    scripts_dir = Path(server.__file__).parent
    stub = root / "stub_server.py"
    stub.write_text(
        _STUB_SERVER_TEMPLATE
        .replace("__SCRIPTS_DIR__", str(scripts_dir))
        .replace("__PROFILES__", str(root / "profiles.json"))
        .replace("__PORT__", str(port)),
        encoding="utf-8",
    )
    log_handle = (root / "stub_server.log").open("w")
    server_proc = subprocess.Popen([sys.executable, str(stub)], stdout=log_handle, stderr=subprocess.STDOUT)
    try:
        base = f"http://127.0.0.1:{port}"
        deadline = time.time() + 60
        ready = False
        while time.time() < deadline and server_proc.poll() is None:
            try:
                with urllib.request.urlopen(f"{base}/health", timeout=2) as response:
                    if json.loads(response.read().decode()).get("service") == "Local ASR":
                        ready = True
                        break
            except OSError:
                time.sleep(0.5)
        assert ready, f"stub server 未就绪，日志：{(root / 'stub_server.log').read_text()[:500]}"

        dirs = {
            "http": root / "out-http",
            "transcribe_cli": root / "out-transcribe-cli",
            "auto_cli": root / "out-auto-cli",
        }
        for directory in dirs.values():
            directory.mkdir()
        md_paths = {name: directory / "out.md" for name, directory in dirs.items()}

        response = requests.post(
            f"{base}/transcribe",
            json={"file_path": str(video), "output_path": str(md_paths["http"])},
            timeout=120,
        )
        assert response.status_code == 200 and response.json().get("success"), response.text[:300]

        for name, cli, args in (
            ("transcribe_cli", "transcribe.py", ["--server", base, "--no-summary"]),
            ("auto_cli", "auto_transcribe.py", ["--api", base, "--no-summary"]),
        ):
            output_flag = "-o"
            process = subprocess.run(
                [sys.executable, str(scripts_dir / cli), str(video), output_flag, str(md_paths[name]), *args],
                capture_output=True, text=True, timeout=300,
            )
            assert process.returncode == 0, f"{cli}: {process.stdout}\\n{process.stderr}"

        refs = {name: _slide_refs(md_paths[name]) for name, path in md_paths.items()}
        assert all(len(items) == 3 for items in refs.values()), refs
        assert refs["http"] == refs["transcribe_cli"] == refs["auto_cli"], "三入口截图引用必须一致"
        for name, directory in dirs.items():
            for ref in refs[name]:
                assert (directory / ref).is_file(), f"{name} 截图文件不存在: {ref}"
            assert (directory / "slides").is_dir()

        # 显式阈值：20 与默认一致；27 只留首帧（与修复前的差异形态一致）
        threshold_outputs = {}
        for label, threshold, expected in (("t20", "20", 3), ("t27", "27", 1)):
            out_dir = root / f"out-{label}"
            out_dir.mkdir()
            run = subprocess.run(
                [sys.executable, str(scripts_dir / "transcribe.py"), str(video),
                 "-o", str(out_dir / "out.md"), "--server", base, "--no-summary",
                 "--slide-threshold", threshold],
                capture_output=True, text=True, timeout=300,
            )
            assert run.returncode == 0, run.stdout + run.stderr
            threshold_refs = _slide_refs(out_dir / "out.md")
            assert len(threshold_refs) == expected, f"阈值 {threshold} 应提取 {expected} 帧，实际 {len(threshold_refs)}"
            assert all((out_dir / ref).is_file() for ref in threshold_refs)
            threshold_outputs[label] = threshold_refs
        assert threshold_outputs["t20"][0] == refs["http"][0], "显式 20 与默认输出应一致"

        # --no-slides：零图但成功产稿
        out_none = root / "out-noslides"
        out_none.mkdir()
        process = subprocess.run(
            [sys.executable, str(scripts_dir / "transcribe.py"), str(video),
             "-o", str(out_none / "out.md"), "--server", base, "--no-summary", "--no-slides"],
            capture_output=True, text=True, timeout=300,
        )
        assert process.returncode == 0
        assert (out_none / "out.md").is_file() and not _slide_refs(out_none / "out.md")
        assert not list(out_none.rglob("*.jpg")), "--no-slides 不得产生截图文件"

        # 批量端点不提取截图（既有能力边界，与 reference 一致）
        batch_in = root / "batch-in"
        batch_in.mkdir()
        shutil.copy(video, batch_in / "lecture.mp4")
        response = requests.post(
            f"{base}/batch_transcribe",
            json={"directory": str(batch_in), "output_dir": str(root / "batch-out")},
            timeout=120,
        )
        body = response.json()
        assert response.status_code == 200 and body.get("success"), response.text[:300]
        batch_md = root / "batch-out" / "lecture.md"
        assert batch_md.is_file() and not _slide_refs(batch_md), "批量端点不应产出截图引用"
        assert not list((root / "batch-out").rglob("*.jpg")), "批量端点不应产出截图文件"

        # 纯音频：默认不调用提取器，无截图产物
        audio = root / "only-audio.wav"
        _write_tone_wav(audio, 3.0)
        out_audio = root / "out-audio"
        out_audio.mkdir()
        response = requests.post(
            f"{base}/transcribe",
            json={"file_path": str(audio), "output_path": str(out_audio / "out.md")},
            timeout=120,
        )
        assert response.status_code == 200 and response.json().get("success"), response.text[:300]
        assert not _slide_refs(out_audio / "out.md"), "纯音频不得产出截图引用"
        assert not list(out_audio.rglob("*.jpg")), "纯音频默认不调用提取器"
    finally:
        server_proc.terminate()
        try:
            server_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server_proc.kill()
        log_handle.close()
    print("Task-022 端到端：HTTP/两 CLI 同视频三帧一致（文件真实存在），阈值 20/27/关闭/批量/纯音频边界全部符合")


def main() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        verify_batch(root)
        verify_slides(root)
        verify_auto_cli_json(root)
        verify_slide_threshold_consistency(root)
        verify_result_file_permissions(root)
        verify_slides_end_to_end(root)
    verify_service_identity()
    print("默认路由、批量错误状态、服务标识、视频场景检测、截图阈值一致性与自动 CLI JSON 回归通过")


if __name__ == "__main__":
    main()
