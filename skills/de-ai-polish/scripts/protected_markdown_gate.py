#!/usr/bin/env python3
"""为 Markdown 图片整行生成快照，并验证改写前后不变量。"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path


SCHEMA_VERSION = 1
CONSTRAINT_ID = "PRESERVE-MARKDOWN-IMAGE-LINES"


class GateError(Exception):
    """输入、快照或受保护区域不满足门禁。"""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def contains_markdown_image(text: str) -> bool:
    """识别至少一个合法的行内 Markdown 图片，支持嵌套括号和转义。"""
    search_from = 0
    while True:
        start = text.find("![", search_from)
        if start < 0:
            return False

        index = start + 2
        bracket_depth = 1
        escaped = False
        while index < len(text) and bracket_depth:
            char = text[index]
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == "[":
                bracket_depth += 1
            elif char == "]":
                bracket_depth -= 1
            index += 1

        if bracket_depth or index >= len(text) or text[index] != "(":
            search_from = start + 2
            continue

        index += 1
        paren_depth = 1
        escaped = False
        while index < len(text) and paren_depth:
            char = text[index]
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == "(":
                paren_depth += 1
            elif char == ")":
                paren_depth -= 1
            index += 1

        if paren_depth == 0:
            return True
        search_from = start + 2


def protected_image_lines(path: Path) -> list[dict[str, object]]:
    if not path.is_file():
        raise GateError(f"Markdown 文件不存在: {path}")

    records: list[dict[str, object]] = []
    in_fence = False
    fence_marker = ""
    for line_number, raw_line in enumerate(path.read_bytes().splitlines(keepends=True), 1):
        text = raw_line.decode("utf-8", errors="strict")
        stripped = text.lstrip()

        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
                fence_marker = ""
            continue

        if in_fence or not contains_markdown_image(text):
            continue

        records.append(
            {
                "ordinal": len(records) + 1,
                "line_number": line_number,
                "sha256": sha256_bytes(raw_line),
                "content_base64": base64.b64encode(raw_line).decode("ascii"),
            }
        )
    return records


def snapshot_payload(source: Path) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "constraint_id": CONSTRAINT_ID,
        "source": {
            "path": str(source.resolve()),
            "sha256": sha256_file(source),
        },
        "protected_image_lines": protected_image_lines(source),
    }


def write_new_json(path: Path, payload: dict[str, object]) -> None:
    if path.exists():
        raise GateError(f"快照已存在，拒绝覆盖: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_snapshot(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise GateError(f"快照不存在: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateError(f"快照无法读取: {exc}") from exc

    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("constraint_id") != CONSTRAINT_ID
        or not isinstance(payload.get("source"), dict)
        or not isinstance(payload.get("protected_image_lines"), list)
    ):
        raise GateError("快照结构或版本非法")
    return payload


def line_hashes(records: list[dict[str, object]]) -> list[str]:
    return [str(item["sha256"]) for item in records]


def compare_records(
    expected: list[dict[str, object]], actual: list[dict[str, object]]
) -> tuple[bool, dict[str, object]]:
    expected_bytes = [
        base64.b64decode(str(item["content_base64"]), validate=True)
        for item in expected
    ]
    actual_bytes = [
        base64.b64decode(str(item["content_base64"]), validate=True)
        for item in actual
    ]
    passed = expected_bytes == actual_bytes
    return passed, {
        "expected_count": len(expected_bytes),
        "actual_count": len(actual_bytes),
        "expected_line_sha256": line_hashes(expected),
        "actual_line_sha256": line_hashes(actual),
    }


def checker_output(
    passed: bool,
    source_sha256: str,
    final_path: Path,
    actual: list[dict[str, object]],
) -> dict[str, object]:
    result_key = "passed_constraint_ids" if passed else "failed_constraint_ids"
    output: dict[str, object] = {
        result_key: [CONSTRAINT_ID],
        "artifact_sha256": {
            "source-markdown": source_sha256,
            "final-markdown": sha256_file(final_path),
        },
        "measurements": {
            CONSTRAINT_ID: {
                "images-preserved": passed,
            }
        },
    }
    if passed:
        output["observables"] = {
            "protected-image-lines": line_hashes(actual),
        }
    return output


def command_snapshot(args: argparse.Namespace) -> int:
    source = Path(args.input).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    payload = snapshot_payload(source)
    write_new_json(output, payload)
    print(
        json.dumps(
            {
                "status": "PROTECTED_MARKDOWN_SNAPSHOT_READY",
                "manifest": str(output),
                "source_sha256": payload["source"]["sha256"],
                "protected_image_line_count": len(payload["protected_image_lines"]),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def command_verify(args: argparse.Namespace) -> int:
    manifest = load_snapshot(Path(args.manifest).expanduser().resolve())
    final_path = Path(args.final).expanduser().resolve()
    actual = protected_image_lines(final_path)
    expected = manifest["protected_image_lines"]
    passed, detail = compare_records(expected, actual)
    output = checker_output(
        passed,
        str(manifest["source"]["sha256"]),
        final_path,
        actual,
    )
    print(json.dumps({"detail": detail}, ensure_ascii=False, sort_keys=True))
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0 if passed else 3


def command_check(args: argparse.Namespace) -> int:
    source = Path(args.source).expanduser().resolve()
    final_path = Path(args.final).expanduser().resolve()
    expected = protected_image_lines(source)
    actual = protected_image_lines(final_path)
    passed, detail = compare_records(expected, actual)
    output = checker_output(passed, sha256_file(source), final_path, actual)
    print(json.dumps({"detail": detail}, ensure_ascii=False, sort_keys=True))
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0 if passed else 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot = subparsers.add_parser("snapshot", help="改写前生成受保护图片整行快照")
    snapshot.add_argument("--input", required=True)
    snapshot.add_argument("--output", required=True)
    snapshot.set_defaults(handler=command_snapshot)

    verify = subparsers.add_parser("verify", help="使用快照验证最终 Markdown")
    verify.add_argument("--manifest", required=True)
    verify.add_argument("--final", required=True)
    verify.set_defaults(handler=command_verify)

    check = subparsers.add_parser("check", help="直接比较源 Markdown 与最终 Markdown")
    check.add_argument("--source", required=True)
    check.add_argument("--final", required=True)
    check.set_defaults(handler=command_check)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.handler(args))
    except (
        GateError,
        OSError,
        UnicodeDecodeError,
        ValueError,
        TypeError,
        KeyError,
    ) as exc:
        print(f"PROTECTED_MARKDOWN_GATE_ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
