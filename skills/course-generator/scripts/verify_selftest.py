#!/usr/bin/env python3
"""Fault-injection regression suite for verify_course.py."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable


SCRIPT_DIR = Path(__file__).resolve().parent
VERIFIER = SCRIPT_DIR / "verify_course.py"


def write_fixture(root: Path) -> None:
    overview_name = "00 示例课程 - 总览.md"
    chapter_name = "01 第一 章（文件名含空格）.md"
    overview_image = "![方法框架](https://example.com/framework.png)"
    image_2 = "![操作界面](https://example.com/step-1.png)"
    image_3 = "![结果页面](https://example.com/step-2.png)"
    root.mkdir(parents=True)
    (root / overview_name).write_text(f"# 示例课程 - 总览\n\n讲师资格的判断属于正常课程内容，不是来源指代。\n\n{overview_image}\n", encoding="utf-8")
    (root / chapter_name).write_text(f"# 第一章\n\n完整说明一次操作链。\n\n{image_2}\n\n操作继续推进。\n\n{image_3}\n", encoding="utf-8")
    (root / "98 图片资产表.md").write_text("# 图片资产表\n\n共三张。\n", encoding="utf-8")
    (root / "99 课程大纲.md").write_text("# 课程大纲\n\n第一章。\n", encoding="utf-8")
    manifest = {
        "schema_version": "1.0",
        "generator_version": "2.8.0",
        "course": {"title": "示例课程"},
        "sources": [{"id": "SRC-001", "path": "转录稿.md"}],
        "overview": {"file": overview_name, "image_ids": ["IMG-001"]},
        "chapters": [{"id": "CH-01", "file": chapter_name, "title": "第一章", "source_refs": ["SRC-001#00:00-10:00"], "material_ids": ["MAT-001"], "image_ids": ["IMG-002", "IMG-003"]}],
        "materials": [{"id": "MAT-001", "type": "操作", "summary": "完整操作链", "source_refs": ["SRC-001#03:20-06:10"], "disposition": "include", "target_chapter_id": "CH-01"}],
        "images": [
            {"id": "IMG-001", "source_ref": "SRC-001#01:20", "original_markdown": overview_image, "body_action": "insert", "target_document_id": "OVERVIEW"},
            {"id": "IMG-002", "source_ref": "SRC-001#04:30", "original_markdown": image_2, "body_action": "insert", "target_document_id": "CH-01"},
            {"id": "IMG-003", "source_ref": "SRC-001#05:10", "original_markdown": image_3, "body_action": "insert", "target_document_id": "CH-01"},
            {"id": "IMG-004", "source_ref": "SRC-001#07:00", "original_markdown": "![会务页](https://example.com/test.png)", "body_action": "asset_only", "target_document_id": None, "reason": "会务测试"}
        ],
        "audit_files": {"outline": "99 课程大纲.md", "image_assets": "98 图片资产表.md"}
    }
    (root / "course-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_verifier(root: Path) -> tuple[int, dict]:
    completed = subprocess.run([sys.executable, str(VERIFIER), str(root)], check=False, capture_output=True, text=True, timeout=20)
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise AssertionError(f"验收器无 stdout，stderr={completed.stderr!r}")
    try:
        result = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise AssertionError(f"stdout 最后一行不是 JSON: {lines[-1]!r}") from exc
    return completed.returncode, result


def mutate_missing_manifest(root: Path) -> None:
    (root / "course-manifest.json").unlink()


def mutate_empty_manifest(root: Path) -> None:
    (root / "course-manifest.json").write_text("{}\n", encoding="utf-8")


def mutate_source_traversal(root: Path) -> None:
    path = root / "course-manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["sources"][0]["path"] = "../../private/secret.md"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mutate_empty_chapter(root: Path) -> None:
    (root / "01 第一 章（文件名含空格）.md").write_text("", encoding="utf-8")


def mutate_missing_image(root: Path) -> None:
    path = root / "01 第一 章（文件名含空格）.md"
    path.write_text(path.read_text(encoding="utf-8").replace("\n\n![结果页面](https://example.com/step-2.png)", ""), encoding="utf-8")


def mutate_wrong_order(root: Path) -> None:
    path = root / "01 第一 章（文件名含空格）.md"
    text = path.read_text(encoding="utf-8")
    image_2 = "![操作界面](https://example.com/step-1.png)"
    image_3 = "![结果页面](https://example.com/step-2.png)"
    path.write_text(text.replace(image_2, "__TMP__").replace(image_3, image_2).replace("__TMP__", image_3), encoding="utf-8")


def mutate_undeclared_image(root: Path) -> None:
    with (root / "01 第一 章（文件名含空格）.md").open("a", encoding="utf-8") as handle:
        handle.write("\n![额外图片](https://example.com/extra.png)\n")


def mutate_material_link(root: Path) -> None:
    path = root / "course-manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["chapters"][0]["material_ids"] = []
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mutate_speaker_actor(root: Path) -> None:
    with (root / "01 第一 章（文件名含空格）.md").open("a", encoding="utf-8") as handle:
        handle.write("\n讲师强调这一步最重要。\n")


def mutate_visible_trace(root: Path) -> None:
    with (root / "01 第一 章（文件名含空格）.md").open("a", encoding="utf-8") as handle:
        handle.write("\n> 原文区间：SRC-001#03:20-06:10\n")


def mutate_asset_only_inserted(root: Path) -> None:
    with (root / "01 第一 章（文件名含空格）.md").open("a", encoding="utf-8") as handle:
        handle.write("\n![会务页](https://example.com/test.png)\n")


def mutate_extra_chapter(root: Path) -> None:
    (root / "02 未声明章节.md").write_text("# 未声明章节\n", encoding="utf-8")


CASES: dict[str, tuple[str, Callable[[Path], None] | None, int, str | None]] = {
    "valid": ("合法近似正例与带空格文件名", None, 0, None),
    "missing-manifest": ("缺少 manifest", mutate_missing_manifest, 1, "CG-CONTRACT-MANIFEST"),
    "empty-manifest": ("空 manifest 对象", mutate_empty_manifest, 1, "CG-CONTRACT-MANIFEST"),
    "source-traversal": ("来源路径穿越", mutate_source_traversal, 1, "CG-CONTRACT-MANIFEST"),
    "empty-chapter": ("空章节", mutate_empty_chapter, 1, "CG-OUTPUT-COMPLETE"),
    "missing-image": ("必插图片缺失", mutate_missing_image, 1, "CG-IMAGE-SET"),
    "wrong-order": ("图片集合相同但顺序错误", mutate_wrong_order, 1, "CG-IMAGE-ORDER"),
    "undeclared-image": ("正文含未声明图片", mutate_undeclared_image, 1, "CG-IMAGE-SET"),
    "material-link": ("素材双向映射断裂", mutate_material_link, 1, "CG-MATERIAL-TRACE"),
    "speaker-actor": ("讲师作为动作发出者", mutate_speaker_actor, 1, "CG-BOOKLIKE-TONE"),
    "visible-trace": ("正文暴露来源审计元数据", mutate_visible_trace, 1, "CG-AUDIT-SEPARATION"),
    "asset-only-inserted": ("仅资产表图片进入正文", mutate_asset_only_inserted, 1, "CG-IMAGE-SET"),
    "extra-chapter": ("存在未声明章节", mutate_extra_chapter, 1, "CG-OUTPUT-COMPLETE"),
}


def run_probe(case_id: str) -> int:
    name, mutation, expected_code, expected_constraint = CASES[case_id]
    with tempfile.TemporaryDirectory(prefix=f"course-generator-probe-{case_id}-") as temp_dir:
        root = Path(temp_dir) / "course"
        write_fixture(root)
        if mutation:
            mutation(root)
        code, result = run_verifier(root)
    result["probe"] = case_id
    result["probe_expectation"] = {"exit_code": expected_code, "constraint_id": expected_constraint}
    print(f"probe={case_id} ({name}), exit={code}")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Course Generator 验收器故障注入回归")
    parser.add_argument("--probe", choices=sorted(CASES), help="只运行一个探针，并透传领域验证器退出码")
    args = parser.parse_args(argv)
    if args.probe:
        return run_probe(args.probe)

    cases = list(CASES.values())
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="course-generator-selftest-") as temp_dir:
        base = Path(temp_dir) / "base"
        write_fixture(base)
        for index, (name, mutation, expected_code, expected_constraint) in enumerate(cases, 1):
            case_root = Path(temp_dir) / f"case-{index:02d}"
            shutil.copytree(base, case_root)
            if mutation:
                mutation(case_root)
            code, result = run_verifier(case_root)
            failed_ids = result.get("failed_constraint_ids", [])
            ok = code == expected_code and (expected_constraint is None or expected_constraint in failed_ids)
            print(f"{'✅' if ok else '❌'} {name}: exit={code}, failed={failed_ids}")
            if not ok:
                failures.append(name)
    summary = {"status": "PASS" if not failures else "FAIL", "case_count": len(cases), "failed_cases": failures}
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
