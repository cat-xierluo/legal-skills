#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
"""认领式声纹注册与识别回归：向量比对、MOSS 转录集成与声纹库读写。

不下载模型：MOSS 推理与 CAM++ 嵌入均以同构 mock 替代；服务端点用
FastAPI TestClient 验证，声纹库路径重定向到临时目录，不触碰本机真实库。
真实录音的注册→识别全流程由用户提供样本后另行验收（Task-014）。
"""

from __future__ import annotations

import tempfile
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

import moss_mlx


def make_wav(path: Path, seconds: int) -> None:
    second = (np.sin(np.arange(moss_mlx.SAMPLE_RATE) * 2 * np.pi * 440 / moss_mlx.SAMPLE_RATE) * 4000).astype("<i2").tobytes()
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(moss_mlx.SAMPLE_RATE)
        for _ in range(seconds):
            wav.writeframes(second)


class FakeModel:
    """输出双人段落的模拟 MOSS 模型。"""

    def generate(self, path, **kwargs):
        with wave.open(path, "rb") as wav:
            duration = wav.getnframes() / wav.getframerate()
        text = (
            f"[0.00][S01]第一人发言[{min(duration, 2):.2f}]"
            f"[{min(duration, 2):.2f}][S02]第二人发言[{min(duration, 4):.2f}]"
        )
        return SimpleNamespace(text=text, generation_tokens=32)


def test_identify_logic() -> None:
    axis_a = np.array([1.0, 0.0], dtype=np.float32)
    axis_b = np.array([0.0, 1.0], dtype=np.float32)
    registry = [
        {"name": "甲", "embedding": axis_a.tolist()},
        {"name": "乙", "embedding": axis_b.tolist()},
    ]
    result = moss_mlx._identify_speakers({"S01": axis_a, "S02": axis_b}, registry)
    assert result["S01"]["name"] == "甲" and result["S01"]["score"] >= 0.99
    assert result["S02"]["name"] == "乙" and result["S02"]["score"] >= 0.99

    # 与两个注册向量都低于阈值：保持匿名
    opposite = {"S01": -axis_a}
    result = moss_mlx._identify_speakers(opposite, registry)
    assert result["S01"] is None

    # 两个标签最接近同一个注册名：仅分数更高者命中，另一个保持匿名
    near_a = np.array([0.995, 0.1], dtype=np.float32)
    near_a = near_a / np.linalg.norm(near_a)
    result = moss_mlx._identify_speakers({"S01": axis_a, "S02": near_a}, registry)
    assert result["S01"]["name"] == "甲"
    assert result["S02"] is None

    # 空库：全部匿名
    result = moss_mlx._identify_speakers({"S01": axis_a}, [])
    assert result["S01"] is None


def test_transcribe_integration() -> None:
    axis_a = np.array([1.0, 0.0], dtype=np.float32)
    axis_b = np.array([0.0, 1.0], dtype=np.float32)
    with tempfile.TemporaryDirectory() as temp_dir:
        source = Path(temp_dir) / "sample.wav"
        make_wav(source, 5)
        vectors = {"S01": axis_a, "S02": axis_b}

        # 库为空：透出 embeddings 供认领，不产出 identification
        with patch.object(moss_mlx, "_speaker_embeddings", return_value=vectors):
            result = moss_mlx.transcribe(
                str(source), FakeModel(),
                speaker_model_factory=lambda: object(),
                diarize=True,
            )
        assert set(result["speaker_embeddings"]) == {"S01", "S02"}
        assert "speaker_identification" not in result

        # 库非空：命中甲、S02 匿名，warnings 汇总识别情况
        profiles = [{"name": "甲", "embedding": axis_a.tolist()}]
        with patch.object(moss_mlx, "_speaker_embeddings", return_value=vectors):
            result = moss_mlx.transcribe(
                str(source), FakeModel(),
                speaker_model_factory=lambda: object(),
                diarize=True,
                speaker_profiles=profiles,
            )
        identification = result["speaker_identification"]
        assert identification["S01"]["name"] == "甲"
        assert identification["S02"] is None
        joined = "；".join(result["_warnings"])
        assert "已识别 S01=甲" in joined and "未识别 S02" in joined

        # 单人快速模式：不提取声纹、不识别
        result = moss_mlx.transcribe(str(source), FakeModel(), diarize=False)
        assert "speaker_embeddings" not in result
        assert "speaker_identification" not in result


def test_registry_file_roundtrip() -> None:
    import server

    with tempfile.TemporaryDirectory() as temp_dir:
        fake_path = Path(temp_dir) / "speaker-profiles.json"
        with patch.object(server, "SPEAKER_PROFILES_PATH", fake_path):
            assert server.load_speaker_profiles() == []
            server.save_speaker_profiles([{"name": "甲", "embedding": [1.0, 0.0]}])
            profiles = server.load_speaker_profiles()
            assert len(profiles) == 1 and profiles[0]["name"] == "甲"

            from fastapi.testclient import TestClient
            client = TestClient(server.app)
            # 端点要求向量至少 16 维（真实 CAM++ 为 192 维），测试用 32 维
            vec_b = [0.0, 2.0] + [0.0] * 30
            # 新注册
            response = client.post("/speaker/register", json={
                "name": "乙", "embedding": vec_b, "source_file": "demo.m4a", "source_label": "S02",
            })
            assert response.status_code == 200 and response.json()["replaced"] is False
            # 同名覆盖（重新认领）
            response = client.post("/speaker/register", json={"name": "乙", "embedding": [0.0, 1.0] + [0.0] * 30})
            assert response.json()["replaced"] is True
            # 列表不含向量本体
            response = client.get("/speaker/list")
            body = response.json()
            assert body["total"] == 2
            assert {item["name"] for item in body["profiles"]} == {"甲", "乙"}
            assert all("embedding" not in item for item in body["profiles"])
            # 删除与重复删除
            assert client.post("/speaker/remove", json={"name": "乙"}).json()["success"] is True
            assert client.post("/speaker/remove", json={"name": "乙"}).status_code == 404
            # 非法输入
            assert client.post("/speaker/register", json={"name": "  ", "embedding": [1.0]}).status_code == 400
            assert client.post("/speaker/register", json={"name": "丙", "embedding": [0.0]}).status_code == 400


def main() -> None:
    test_identify_logic()
    test_transcribe_integration()
    test_registry_file_roundtrip()
    print("声纹注册与识别回归通过（向量逻辑 / 转录集成 / 库读写与端点）")


if __name__ == "__main__":
    main()
