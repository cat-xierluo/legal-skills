"""不下载模型的 MOSS 适配器回归：分段、校验和跨段说话人映射。"""

from __future__ import annotations

import tempfile
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

try:
    import numpy as np
except ImportError as exc:
    raise SystemExit("缺少 NumPy；请先运行 python3 -m pip install -r assets/requirements.txt") from exc

import moss_mlx


class FakeModel:
    def __init__(self):
        self.calls = 0

    def generate(self, path, **kwargs):
        self.calls += 1
        assert kwargs["max_tokens"] == moss_mlx.MAX_OUTPUT_TOKENS
        assert "请求权基础" in kwargs["prompt"]
        with wave.open(path, "rb") as wav:
            duration = wav.getnframes() / wav.getframerate()
        return SimpleNamespace(
            text=f"[0.00][S01]请求权基础[{min(duration, 2):.2f}]",
            generation_tokens=32,
        )


def make_wav(path: Path, seconds: int) -> None:
    second = (np.sin(np.arange(moss_mlx.SAMPLE_RATE) * 2 * np.pi * 440 / moss_mlx.SAMPLE_RATE) * 4000).astype("<i2").tobytes()
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(moss_mlx.SAMPLE_RATE)
        for _ in range(seconds):
            wav.writeframes(second)


def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        source = Path(temp_dir) / "sample.wav"
        make_wav(source, 3)
        model = FakeModel()
        result = moss_mlx.transcribe(str(source), model, hotwords=["请求权基础"])
        assert model.calls == 1
        assert result["sentence_info"][0] == {
            "start": 0, "end": 2000, "sentence": "请求权基础", "spk": "S01"
        }
        assert result["speaker_scope"] == "global"

        class ShortSpeakerModel:
            def generate(self, path, **kwargs):
                return SimpleNamespace(
                    text="[0.00][S01]第一位[1.00][1.00][S02]第二位[2.00]",
                    generation_tokens=20,
                )

        result = moss_mlx.transcribe(str(source), ShortSpeakerModel())
        assert len(result["_warnings"]) == 2
        assert all("匿名标签可能不稳定" in item for item in result["_warnings"])

        for malformed in (
            "[0.00][S01]不完整",
            "[0.00][S01]文字[2.00]尾巴",
            "[2.99][S01]文字[4.00]",
        ):
            try:
                moss_mlx._parse_output(SimpleNamespace(text=malformed), 3)
            except RuntimeError:
                pass
            else:
                raise AssertionError("不完整输出被错误接受")

        silent = Path(temp_dir) / "silent.wav"
        with wave.open(str(silent), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(moss_mlx.SAMPLE_RATE)
            wav.writeframes(b"\0\0" * moss_mlx.SAMPLE_RATE)
        assert moss_mlx._is_near_silent(silent)
        assert not moss_mlx._is_near_silent(source)
        kept, removed = moss_mlx._discard_near_silent(
            silent, [{"start": 0.0, "end": 0.5, "speaker": "S01", "text": "嗯"}]
        )
        assert not kept and removed == 1

        make_wav(source, moss_mlx.CHUNK_SECONDS + 10)
        model = FakeModel()
        vectors = {"S01": np.array([1.0, 0.0], dtype=np.float32)}
        with patch.object(moss_mlx, "_speaker_embeddings", return_value=vectors):
            result = moss_mlx.transcribe(
                str(source), model,
                speaker_model_factory=lambda: object(),
                hotwords=["请求权基础"],
            )
        assert model.calls == 2
        assert len(result["sentence_info"]) == 2
        assert {segment["spk"] for segment in result["sentence_info"]} == {"S01"}
        assert result["sentence_info"][1]["start"] >= moss_mlx.CHUNK_SECONDS * 1000 - 15000

        sparse = Path(temp_dir) / "sparse.wav"
        with wave.open(str(source), "rb") as sample:
            second = sample.readframes(moss_mlx.SAMPLE_RATE)
        with wave.open(str(sparse), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(moss_mlx.SAMPLE_RATE)
            wav.writeframes(second * 2)
            wav.writeframes(b"\0\0" * moss_mlx.SAMPLE_RATE * 118)
            wav.writeframes(second * 2)
            wav.writeframes(b"\0\0" * moss_mlx.SAMPLE_RATE * 8)
        model = FakeModel()
        split_points = [0, 60 * moss_mlx.SAMPLE_RATE, 120 * moss_mlx.SAMPLE_RATE, 130 * moss_mlx.SAMPLE_RATE]
        with patch.object(moss_mlx, "_split_points", return_value=split_points), \
                patch.object(moss_mlx, "_speaker_embeddings", return_value=vectors):
            result = moss_mlx.transcribe(
                str(sparse), model,
                speaker_model_factory=lambda: object(),
                hotwords=["请求权基础"],
            )
        assert model.calls == 2
        assert len(result["sentence_info"]) == 2
        assert any("已跳过模型推理" in warning for warning in result["_warnings"])
    print("MOSS 适配器回归通过（使用合成音频和模拟模型）")


if __name__ == "__main__":
    main()
