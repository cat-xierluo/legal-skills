#!/usr/bin/env python3
"""Regression tests for index_sources.py using only temporary fixtures."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from index_sources import build_index


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="course-generator-index-selftest-") as temp_dir:
        root = Path(temp_dir)
        source = root / "单文件.md"
        source.write_text(
            "# 标题\n\n发言人1 00:01\n第一段包含真实方法与结果。\n\n"
            "![图](https://example.com/a.png)\n\n> *00:15*\n\n第二段继续说明限制条件。\n\n"
            "Speaker 2 00:20 同行发言人标记后的实质内容不得丢失。\n",
            encoding="utf-8",
        )
        output = root / "single-index.json"
        result = build_index(source, output)
        kinds = [block["kind"] for block in result["sources"][0]["blocks"]]
        expected = ["heading", "speaker", "content", "image", "timestamp", "content", "content"]
        if kinds != expected:
            failures.append(f"单文件分类错误: {kinds!r}")
        content_ids = [block["id"] for block in result["sources"][0]["blocks"] if block["kind"] == "content"]
        if content_ids != ["BLK-00003", "BLK-00006", "BLK-00007"]:
            failures.append(f"block ID 不稳定: {content_ids!r}")
        if "实质内容不得丢失" not in result["sources"][0]["blocks"][-1]["preview"]:
            failures.append("同行发言人标记后的内容被错当成 speaker 跳过")
        first_sha = file_sha(output)
        build_index(source, output)
        if file_sha(output) != first_sha:
            failures.append("同输入重复索引的字节结果不一致")

        multi_image_source = root / "同行图片.md"
        multi_image_source.write_text(
            "![步骤一](https://example.com/1.png) ![步骤二](https://example.com/2.png)\n",
            encoding="utf-8",
        )
        multi_image_result = build_index(multi_image_source, root / "multi-image-index.json")
        multi_image_blocks = multi_image_result["sources"][0]["blocks"]
        if [block["kind"] for block in multi_image_blocks] != ["image", "image"]:
            failures.append(f"同行多图未拆成独立 image block: {multi_image_blocks!r}")

        transcript_bundle = root / "平台转录包.md"
        transcript_bundle.write_text(
            "# 课程\n\n## 转录内容\n\n真实讲课正文包含一个可复用方法。\n\n"
            "## 关键词\n\n自动关键词，不是独立证据。\n\n"
            "## 议程摘要\n\n平台自动归纳出的议程内容。\n",
            encoding="utf-8",
        )
        transcript_result = build_index(transcript_bundle, root / "transcript-index.json")
        transcript_blocks = transcript_result["sources"][0]["blocks"]
        content_previews = [block["preview"] for block in transcript_blocks if block["kind"] == "content"]
        derived_previews = [block["preview"] for block in transcript_blocks if block["kind"] == "derived"]
        if content_previews != ["真实讲课正文包含一个可复用方法。"]:
            failures.append(f"平台附录污染 content 覆盖基线: {content_previews!r}")
        if not any("自动关键词" in preview for preview in derived_previews) or not any("平台自动归纳" in preview for preview in derived_previews):
            failures.append(f"平台附录未标为 derived: {derived_previews!r}")

        source_dir = root / "sources"
        source_dir.mkdir()
        (source_dir / "b.txt").write_text("B 内容。\n", encoding="utf-8")
        (source_dir / "a.md").write_text("A 内容。\n", encoding="utf-8")
        (source_dir / ".hidden.md").write_text("隐藏内容。\n", encoding="utf-8")
        directory_output = root / "directory-index.json"
        directory_result = build_index(source_dir, directory_output)
        paths = [item["path"] for item in directory_result["sources"]]
        if paths != ["a.md", "b.txt"]:
            failures.append(f"目录来源排序或排除规则错误: {paths!r}")

        generated_dir = source_dir / "generated-course"
        generated_dir.mkdir()
        (generated_dir / "00 旧课程.md").write_text("不应重新进入来源索引。\n", encoding="utf-8")
        nested_output = generated_dir / "source-index.json"
        nested_result = build_index(source_dir, nested_output)
        nested_paths = [item["path"] for item in nested_result["sources"]]
        if nested_paths != ["a.md", "b.txt"]:
            failures.append(f"输出目录未从来源发现中排除: {nested_paths!r}")

    status = "PASS" if not failures else "FAIL"
    print(json.dumps({"status": status, "case_count": 7, "failures": failures}, ensure_ascii=False, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
