#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
"""认领式声纹注册与识别回归（Task-016 审计整改版）。

覆盖：
- Task-017：向量输入校验（维度/有限性/范数/float32 溢出）、坏条目隔离、识别故障降级
- Task-018：声纹库原子保存、损坏保护、进程间并发安全、文件权限
- Task-019：完整说话人状态契约（空库/部分命中/短发言/提取失败/主动关闭）

不下载模型：MOSS 推理与 CAM++ 嵌入均以同构 mock 替代；服务端点用
FastAPI TestClient 验证，声纹库路径重定向到临时目录，不触碰本机真实库。
真实录音的注册→识别全流程由用户提供样本后另行验收（Task-014/024）。
"""

from __future__ import annotations

import io
import json
import tempfile
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

import moss_mlx
import speaker_store


def make_wav(path: Path, seconds: int) -> None:
    second = (np.sin(np.arange(moss_mlx.SAMPLE_RATE) * 2 * np.pi * 440 / moss_mlx.SAMPLE_RATE) * 4000).astype("<i2").tobytes()
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(moss_mlx.SAMPLE_RATE)
        for _ in range(seconds):
            wav.writeframes(second)


def unit_vec(axis: int, dim: int = speaker_store.EXPECTED_EMBEDDING_DIM) -> np.ndarray:
    vec = np.zeros(dim, dtype=np.float32)
    vec[axis] = 1.0
    return vec


class FakeModel:
    """输出多说话人段落的模拟 MOSS 模型。"""

    def __init__(self, speakers: tuple[str, ...] = ("S01", "S02")):
        self.speakers = speakers

    def generate(self, path, **kwargs):
        with wave.open(path, "rb") as wav:
            duration = wav.getnframes() / wav.getframerate()
        chunks = []
        step = min(2.0, duration / max(len(self.speakers), 1))
        cursor = 0.0
        for index, spk in enumerate(self.speakers):
            end = duration if index == len(self.speakers) - 1 else min(cursor + step, duration)
            chunks.append(f"[{cursor:.2f}][{spk}]第{index + 1}位发言[{end:.2f}]")
            cursor = end
        return SimpleNamespace(text="".join(chunks), generation_tokens=32)


def test_embedding_validation() -> None:
    """Task-017：按模型维度/有限性/范数显式校验，非法输入全部拒绝。"""
    good = unit_vec(0)
    assert speaker_store.validate_embedding(good.tolist()).shape == (speaker_store.EXPECTED_EMBEDDING_DIM,)
    # 数值未归一的向量返回单位向量
    scaled = speaker_store.validate_embedding((good * 7.5).tolist())
    assert abs(float(np.linalg.norm(scaled)) - 1.0) < 1e-5
    bad_cases = {
        "16 维": ([1.0] + [0.0] * 15),
        "32 维": ([1.0] + [0.0] * 31),
        "191 维": ([1.0] * 191),
        "193 维": ([1.0] * 193),
        "空向量": [],
        "全零": ([0.0] * speaker_store.EXPECTED_EMBEDDING_DIM),
        "NaN": ([float("nan")] + [0.0] * (speaker_store.EXPECTED_EMBEDDING_DIM - 1)),
        "Inf": ([float("inf")] + [0.0] * (speaker_store.EXPECTED_EMBEDDING_DIM - 1)),
        "float32 溢出": ([1e40] + [0.0] * (speaker_store.EXPECTED_EMBEDDING_DIM - 1)),
        "非数值": (["x"] * speaker_store.EXPECTED_EMBEDDING_DIM),
    }
    for label, raw in bad_cases.items():
        try:
            speaker_store.validate_embedding(raw)
        except ValueError:
            continue
        raise AssertionError(f"{label} 向量未被拒绝")
    print("Task-017 向量校验：维度/空/零/NaN/Inf/溢出/非数值全部拒绝，正常 192 维归一化通过")


def test_identify_logic() -> None:
    """Task-017：识别返回 (identification, issues)；坏条目只隔离不抛错。"""
    axis_a, axis_b = unit_vec(0), unit_vec(1)
    registry = [
        {"name": "甲", "embedding": axis_a.tolist()},
        {"name": "乙", "embedding": axis_b.tolist()},
    ]
    result, issues = moss_mlx._identify_speakers({"S01": axis_a, "S02": axis_b}, registry)
    assert not issues
    assert result["S01"]["name"] == "甲" and result["S01"]["score"] >= 0.99
    assert result["S02"]["name"] == "乙" and result["S02"]["score"] >= 0.99

    # 与两个注册向量都低于阈值：保持匿名
    result, _ = moss_mlx._identify_speakers({"S01": -axis_a}, registry)
    assert result["S01"] is None

    # 两个标签最接近同一个注册名：仅分数更高者命中
    near_a = np.array([0.995, 0.1] + [0.0] * (speaker_store.EXPECTED_EMBEDDING_DIM - 2), dtype=np.float32)
    near_a = near_a / np.linalg.norm(near_a)
    result, _ = moss_mlx._identify_speakers({"S01": axis_a, "S02": near_a}, registry)
    assert result["S01"]["name"] == "甲" and result["S02"] is None

    # 空库：全部匿名且无 issue
    result, issues = moss_mlx._identify_speakers({"S01": axis_a}, [])
    assert result["S01"] is None and not issues

    # 坏条目（32 维/NaN/缺名字/非对象）混入：隔离进 issues，其他人正常识别
    dirty_registry = [
        {"name": "坏维度", "embedding": [1.0] * 32},
        {"name": "坏数值", "embedding": [float("nan")] + [0.0] * (speaker_store.EXPECTED_EMBEDDING_DIM - 1)},
        {"embedding": axis_b.tolist()},
        "not-a-dict",
        {"name": "甲", "embedding": axis_a.tolist()},
    ]
    result, issues = moss_mlx._identify_speakers({"S01": axis_a, "S02": axis_b}, dirty_registry)
    assert len(issues) == 4, issues
    assert all("隔离" in issue for issue in issues)
    assert result["S01"]["name"] == "甲"
    assert result["S02"] is None  # 乙的条目缺名字被隔离，S02 不应命中
    print("Task-017 识别逻辑：坏条目隔离 4 类并告警，有效条目正常命中，阈值/同名唯一分配不变")


def test_transcribe_states() -> None:
    """Task-019：空库/部分命中/短发言/提取失败/关闭都有完整逐人状态。"""
    axis_a, axis_b = unit_vec(0), unit_vec(1)
    with tempfile.TemporaryDirectory() as temp_dir:
        source = Path(temp_dir) / "sample.wav"
        make_wav(source, 5)
        vectors = {"S01": axis_a, "S02": axis_b}

        # 空库：identification 逐人 null + speaker_states 全 unknown + embeddings 供认领
        with patch.object(moss_mlx, "_speaker_embeddings", return_value=vectors):
            result = moss_mlx.transcribe(
                str(source), FakeModel(("S01", "S02")),
                speaker_model_factory=lambda: object(),
                diarize=True, speaker_profiles=[],
            )
        assert result["speaker_identification"] == {"S01": None, "S02": None}
        assert set(result["speaker_embeddings"]) == {"S01", "S02"}
        assert all(state["status"] == "unknown" for state in result["speaker_states"].values())

        # 部分命中：S01 命中甲，S02 unknown；warnings 汇总
        profiles = [{"name": "甲", "embedding": axis_a.tolist()}]
        with patch.object(moss_mlx, "_speaker_embeddings", return_value=vectors):
            result = moss_mlx.transcribe(
                str(source), FakeModel(("S01", "S02")),
                speaker_model_factory=lambda: object(),
                diarize=True, speaker_profiles=profiles,
            )
        assert result["speaker_identification"]["S01"]["name"] == "甲"
        assert result["speaker_identification"]["S02"] is None
        assert result["speaker_states"]["S01"]["status"] == "matched"
        assert result["speaker_states"]["S01"]["name"] == "甲"
        assert result["speaker_states"]["S02"]["status"] == "unknown"
        joined = "；".join(result["_warnings"])
        assert "已识别 S01=甲" in joined and "未识别 S02" in joined

        # 短发言：S02 全程不足 3 秒 → insufficient_audio，不出现在识别表但仍在状态里
        short_output = SimpleNamespace(
            text="[0.00][S01]第一人长篇发言[4.00][4.00][S02]嗯[4.50]",
            generation_tokens=32,
        )
        short_model = SimpleNamespace(generate=lambda path, **kwargs: short_output)
        with patch.object(moss_mlx, "_speaker_embeddings", return_value={"S01": axis_a}):
            result = moss_mlx.transcribe(
                str(source), short_model,
                speaker_model_factory=lambda: object(),
                diarize=True, speaker_profiles=profiles,
            )
        assert set(result["speaker_states"]) == {"S01", "S02"}
        assert result["speaker_states"]["S01"]["status"] == "matched"
        assert result["speaker_states"]["S02"]["status"] == "insufficient_audio"
        assert "可经用户确认后认领" not in result["speaker_states"]["S02"]["detail"]
        assert "只能为本稿命名" in result["speaker_states"]["S02"]["detail"]

        # 提取失败：降级 extraction_failed，仍产稿
        def broken_factory():
            raise RuntimeError("CAM++ 加载失败")

        with patch.object(moss_mlx, "_speaker_embeddings", side_effect=RuntimeError("提取异常")):
            result = moss_mlx.transcribe(
                str(source), FakeModel(("S01", "S02")),
                speaker_model_factory=broken_factory,
                diarize=True, speaker_profiles=profiles,
            )
        assert result["speaker_identification"] == {"S01": None, "S02": None}
        assert all(state["status"] == "extraction_failed" for state in result["speaker_states"].values())
        assert any("声纹提取失败" in warning for warning in result["_warnings"])

        # 显式关闭提取：disabled，不谎报为未识别
        with patch.object(moss_mlx, "SPEAKER_EMBEDDINGS_ENABLED", False):
            result = moss_mlx.transcribe(
                str(source), FakeModel(("S01", "S02")),
                speaker_model_factory=lambda: object(),
                diarize=True, speaker_profiles=profiles,
            )
        assert all(state["status"] == "disabled" for state in result["speaker_states"].values())
        assert "speaker_identification" in result  # 仍逐人 null，不缺字段

        # fast 模式：disabled 状态
        result = moss_mlx.transcribe(str(source), FakeModel(("S01",)), diarize=False)
        assert all(state["status"] == "disabled" for state in result["speaker_states"].values())
        assert "speaker_embeddings" not in result
        assert "speaker_identification" not in result

        # 识别步骤异常：降级全匿名且不抛错（Task-017 故障隔离）
        with patch.object(moss_mlx, "_identify_speakers", side_effect=RuntimeError("boom")), \
             patch.object(moss_mlx, "_speaker_embeddings", return_value=vectors):
            result = moss_mlx.transcribe(
                str(source), FakeModel(("S01", "S02")),
                speaker_model_factory=lambda: object(),
                diarize=True, speaker_profiles=profiles,
            )
        assert result["speaker_identification"] == {"S01": None, "S02": None}
        assert all(state["status"] == "extraction_failed" for state in result["speaker_states"].values())
        assert any("识别步骤失败" in warning for warning in result["_warnings"])
    print("Task-019 说话人状态：空库/部分命中/短发言/提取失败/关闭/fast 六路契约全部满足")


def test_registry_file_roundtrip() -> None:
    """Task-017/018：端点校验、原子保存、损坏保护与并发（TestClient + 子进程）。"""
    import os
    import stat
    import server

    with tempfile.TemporaryDirectory() as temp_dir:
        fake_path = Path(temp_dir) / "speaker-profiles.json"
        with patch.object(server, "SPEAKER_PROFILES_PATH", fake_path):
            assert server.load_speaker_profiles() == []
            vec_a = unit_vec(0).tolist()
            vec_b = unit_vec(1).tolist()
            server.save_speaker_profiles([{"name": "甲", "embedding": vec_a}])
            profiles = server.load_speaker_profiles()
            assert len(profiles) == 1 and profiles[0]["name"] == "甲"

            from fastapi.testclient import TestClient
            client = TestClient(server.app, raise_server_exceptions=False)
            # 新注册（192 维有效）
            response = client.post("/speaker/register", json={
                "name": "乙", "embedding": vec_b, "source_file": "demo.m4a", "source_label": "S02",
            })
            assert response.status_code == 200 and response.json()["replaced"] is False
            # 同名覆盖（重新认领）
            response = client.post("/speaker/register", json={"name": "乙", "embedding": unit_vec(2).tolist()})
            assert response.json()["replaced"] is True
            # 列表不含向量本体
            response = client.get("/speaker/list")
            body = response.json()
            assert body["total"] == 2
            assert {item["name"] for item in body["profiles"]} == {"甲", "乙"}
            assert all("embedding" not in item for item in body["profiles"])

            # Task-017：非法向量一律 400 且库文件字节不变
            before = fake_path.read_bytes()
            bad_vectors = [
                ("32 维", [1.0] + [0.0] * 31),
                ("191 维", [1.0] * 191),
                ("193 维", [1.0] * 193),
                ("全零", [0.0] * 192),
                ("溢出", [1e40] + [0.0] * 191),
                ("单值", [1.0]),
            ]
            for label, bad in bad_vectors:
                response = client.post("/speaker/register", json={"name": "丙", "embedding": bad})
                assert response.status_code == 400, (label, response.status_code)
            # NaN/Inf：httpx 的 json= 不允许非有限值，用原始 JSON 字面量直接打服务端
            for literal in ("NaN", "Infinity"):
                raw_body = json.dumps({"name": "丙", "embedding": ["PLACEHOLDER"] * 192}).replace(
                    '"PLACEHOLDER"', literal, 1
                )
                response = client.post(
                    "/speaker/register",
                    content=raw_body.encode(),
                    headers={"Content-Type": "application/json"},
                )
                # pydantic 层拒绝为 422、显式校验拒绝为 400，均为明确 4xx
                assert response.status_code in (400, 422), (literal, response.status_code)
            assert client.post("/speaker/register", json={"name": "  ", "embedding": vec_a}).status_code == 400
            assert fake_path.read_bytes() == before

            # Task-018：写入中断后旧库字节不变，注册不被静默当作空库
            def interrupted_dump(payload, stream, **kwargs):
                stream.write('{"version":')
                raise OSError("synthetic interrupted write")

            original_dump = json.dump
            with patch.object(speaker_store.json, "dump", side_effect=interrupted_dump):
                try:
                    server.save_speaker_profiles([{"name": "示例新项", "embedding": vec_b}])
                except OSError:
                    pass
            assert fake_path.read_bytes() == before
            assert len(server.load_speaker_profiles()) == 2

            # 损坏库：读取降级告警，注册/删除拒绝（409）并保留原件
            corrupt_bytes = "{broken-json"
            fake_path.write_text(corrupt_bytes)
            profiles, issues, corrupt = speaker_store.load_profiles(fake_path)
            assert profiles == [] and corrupt and issues
            response = client.post("/speaker/register", json={"name": "丁", "embedding": vec_a})
            assert response.status_code == 409, response.status_code
            assert client.post("/speaker/remove", json={"name": "甲"}).status_code == 409
            assert fake_path.read_text() == corrupt_bytes

            # 删除与重复删除（恢复正常库后）
            fake_path.write_bytes(before)
            assert client.post("/speaker/remove", json={"name": "乙"}).json()["success"] is True
            assert client.post("/speaker/remove", json={"name": "乙"}).status_code == 404

            # 权限：库与锁文件仅当前用户可读写
            mode = stat.S_IMODE(fake_path.stat().st_mode)
            assert mode & 0o077 == 0, oct(mode)
            lock_path = fake_path.parent / f".{fake_path.name}.lock"
            if lock_path.exists():
                assert stat.S_IMODE(lock_path.stat().st_mode) & 0o077 == 0

    # Task-018：两个独立进程并发注册不同名字不丢项
    with tempfile.TemporaryDirectory() as temp_dir:
        shared_path = Path(temp_dir) / "shared-profiles.json"
        speaker_store.save_profiles(shared_path, [])
        import multiprocessing as mp

        def worker(axis: int, path_str: str, ready, go):
            vec = unit_vec(axis)
            def _mutate(profiles, _issues):
                profiles.append(speaker_store.build_entry(f"并发{axis}", vec))
                return profiles, None
            ready.set()
            go.wait()
            for _ in range(3):
                speaker_store.mutate_profiles(Path(path_str), _mutate)
                break

        ctx = mp.get_context("fork")
        ready_a, ready_b, go = ctx.Event(), ctx.Event(), ctx.Event()
        proc_a = ctx.Process(target=worker, args=(0, str(shared_path), ready_a, go))
        proc_b = ctx.Process(target=worker, args=(1, str(shared_path), ready_b, go))
        proc_a.start(); proc_b.start()
        ready_a.wait(10); ready_b.wait(10)
        go.set()
        proc_a.join(30); proc_b.join(30)
        assert proc_a.exitcode == 0 and proc_b.exitcode == 0
        profiles, issues, corrupt = speaker_store.load_profiles(shared_path)
        assert not corrupt and not issues, (issues, corrupt)
        assert {item["name"] for item in profiles} == {"并发0", "并发1"}, profiles
    print("Task-017/018 端点与存储：校验 400/损坏 409/原子保全/并发不丢项/文件权限全部通过")


def main() -> None:
    test_embedding_validation()
    test_identify_logic()
    test_transcribe_states()
    test_registry_file_roundtrip()
    print("声纹注册与识别回归通过（输入校验 / 故障隔离 / 存储安全 / 并发 / 说话人状态契约）")


if __name__ == "__main__":
    main()
