#!/usr/bin/env python3
"""校验并打包行业报告或客户简报为 HTML、A4 PDF 与证据元数据。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parent.parent


def _run(command: list[str]) -> None:
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"命令失败({result.returncode}): {' '.join(command)}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _urls(text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"https?://[^\s<>\])}，。；、]+", text)))


def _profile_value(path: Path, key: str, fallback: str = "") -> str:
    if not path.is_file():
        return fallback
    match = re.search(rf"(?m)^-\s+{re.escape(key)}\s*:\s*(.+?)(?:\s+#.*)?$", path.read_text(encoding="utf-8"))
    return match.group(1).strip().strip('"\'') if match else fallback


def _profile_error(profile: Path) -> str | None:
    for key in ("law_firm", "lead_lawyer"):
        value = _profile_value(profile, key)
        lowered = value.lower()
        if not value or "占位" in value or "placeholder" in lowered or value.startswith("XX"):
            return f"profile 必填字段 {key} 尚未填写"
    for key in ("contact_wechat", "contact_phone"):
        value = _profile_value(profile, key)
        if value and ("占位" in value or "placeholder" in value.lower()):
            return f"profile 字段 {key} 仍是占位值；不需要时请留空"
    return None


def _write_checklist(target: Path, profile: Path, start: str, end: str, cadence: str) -> None:
    template = SKILL_DIR / "templates" / "checklist-template.md"
    if not template.is_file():
        return
    text = template.read_text(encoding="utf-8")
    replacements = {
        "{editor}": "待人工签署",
        "{period_start}": start,
        "{period_end}": end,
        "{cadence}": cadence,
        "{cover_style}": _profile_value(profile, "cover_style", "W1-minimal"),
        "{YYYY-MM-DD HH:MM}": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    target.write_text(text, encoding="utf-8")


def _required_file(path_text: str | None, label: str) -> Path:
    if not path_text:
        raise ValueError(f"缺少 {label}")
    path = Path(path_text).resolve()
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"{label} 不存在或为空: {path}")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="报告构建入口: validate → HTML → PDF → meta")
    parser.add_argument("--input", "-i", required=True, help="已完成的 Markdown")
    parser.add_argument("--kind", choices=("report", "brief"), required=True)
    parser.add_argument("--profile", default=str(SKILL_DIR / "config" / "report-profile.md"))
    parser.add_argument("--whitelist", default=str(SKILL_DIR / "config" / "sources-whitelist.txt"))
    parser.add_argument("--audience-profile", default=str(SKILL_DIR / "config" / "audience-profile.md"))
    parser.add_argument("--moments-copy", help="brief 必需：朋友圈 DRAFT Markdown")
    parser.add_argument("--wechat-draft", help="brief 必需：公众号 DRAFT Markdown")
    parser.add_argument("--cadence", choices=("daily", "weekly", "event"), help="brief 必需")
    parser.add_argument("--period-start", help="brief 信息窗口起始日 YYYY-MM-DD")
    parser.add_argument("--period-end", help="brief 信息窗口结束日 YYYY-MM-DD")
    parser.add_argument("--output-dir", help="派生文件目录，默认与输入文件相同")
    parser.add_argument("--force", action="store_true", help="覆盖同名派生文件")
    args = parser.parse_args()

    try:
        source = _required_file(args.input, "输入 Markdown")
        profile = _required_file(args.profile, "品牌配置")
    except ValueError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2
    if profile_error := _profile_error(profile):
        print(f"[error] {profile_error}", file=sys.stderr)
        return 2
    configured_kind = _profile_value(profile, "report_kind")
    if configured_kind != args.kind:
        print(f"[error] profile 的 report_kind={configured_kind or '未设置'}，与 --kind {args.kind} 不一致", file=sys.stderr)
        return 2

    whitelist = Path(args.whitelist).resolve()
    audience_profile = Path(args.audience_profile).resolve()
    moments = None
    wechat = None
    if args.kind == "brief":
        try:
            whitelist = _required_file(args.whitelist, "信源白名单")
            audience_profile = _required_file(args.audience_profile, "客户画像")
            moments = _required_file(args.moments_copy, "朋友圈草稿")
            wechat = _required_file(args.wechat_draft, "公众号草稿")
        except ValueError as exc:
            print(f"[error] {exc}", file=sys.stderr)
            return 2
        if not args.cadence or not args.period_start or not args.period_end:
            print("[error] client brief 必须提供 --cadence、--period-start 和 --period-end", file=sys.stderr)
            return 2
        try:
            start = date.fromisoformat(args.period_start)
            end = date.fromisoformat(args.period_end)
        except ValueError:
            print("[error] 日期必须使用 YYYY-MM-DD", file=sys.stderr)
            return 2
        if start > end:
            print("[error] 起始日不能晚于结束日", file=sys.stderr)
            return 2

    output_dir = Path(args.output_dir).resolve() if args.output_dir else source.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    html_path = output_dir / f"{source.stem}.html"
    pdf_path = output_dir / f"{source.stem}.pdf"
    meta_path = output_dir / f"{source.stem}.meta.json"
    checklist_path = output_dir / f"{source.stem}.checklist.md"
    outputs = [html_path, pdf_path, meta_path] + ([checklist_path] if args.kind == "brief" else [])
    existing = [str(path) for path in outputs if path.exists()]
    if existing and not args.force:
        print(f"[error] 派生文件已存在；复核后使用 --force 重建: {', '.join(existing)}", file=sys.stderr)
        return 2

    validate_command = [sys.executable, str(SKILL_DIR / "scripts" / "validate_report.py"), "--input", str(source), "--kind", args.kind]
    if args.kind == "brief":
        validate_command.extend(["--whitelist", str(whitelist), "--period-start", args.period_start, "--period-end", args.period_end])

    try:
        _run(validate_command)
        if args.kind == "brief" and moments and wechat:
            _run([sys.executable, str(SKILL_DIR / "scripts" / "validate_channels.py"), "--moments", str(moments), "--wechat", str(wechat), "--whitelist", str(whitelist), "--brief", str(source)])
        render_command = [
            sys.executable,
            str(SKILL_DIR / "scripts" / "render.py"),
            "--input", str(source),
            "--output", str(html_path),
            "--profile", str(profile),
            "--report-kind", args.kind,
        ]
        if args.kind == "brief":
            render_command.extend(["--period-start", args.period_start, "--period-end", args.period_end, "--cadence", args.cadence])
        _run(render_command)
        _run([sys.executable, str(SKILL_DIR / "scripts" / "pdf.py"), "--input", str(html_path), "--output", str(pdf_path), "--profile", str(profile)])
    except RuntimeError as exc:
        print(f"[error] 构建中止: {exc}", file=sys.stderr)
        return 1

    input_text = source.read_text(encoding="utf-8")
    artifacts = {
        "source_markdown": {"path": str(source), "sha256": _sha256(source)},
        "html": {"path": str(html_path), "sha256": _sha256(html_path)},
        "pdf": {"path": str(pdf_path), "sha256": _sha256(pdf_path)},
    }
    if moments and wechat:
        artifacts["moments_copy"] = {"path": str(moments), "sha256": _sha256(moments)}
        artifacts["wechat_draft"] = {"path": str(wechat), "sha256": _sha256(wechat)}

    metadata = {
        "schema_version": 2,
        "kind": args.kind,
        "status": "DRAFT" if args.kind == "brief" else "PUBLIC_REVIEW",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "artifacts": artifacts,
        "source_urls": _urls(input_text),
        "cadence": args.cadence if args.kind == "brief" else None,
        "period_window": ({"start": args.period_start, "end": args.period_end} if args.kind == "brief" else None),
        "config_sha256": {
            "report_profile": _sha256(profile),
            **({"audience_profile": _sha256(audience_profile), "whitelist": _sha256(whitelist)} if args.kind == "brief" else {}),
        },
    }
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.kind == "brief":
        _write_checklist(checklist_path, profile, args.period_start, args.period_end, args.cadence)
    print(f"构建完成: {pdf_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
