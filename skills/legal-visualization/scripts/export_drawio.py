#!/usr/bin/env python3
"""export_drawio.py - Legal Visualization drawio 批量导出脚本。

检测本机 drawio CLI，调用 drawio --export 把 .drawio 导出为 SVG/PNG/PDF。
默认将 .drawio 源文件、SVG、PNG 与 export-report.json 写入 archive/<timestamp>/。
SVG/PNG 均由 draw.io / diagrams.net 从 .drawio 导出。PNG 默认按 2.0 倍导出，记录 size_bytes、image_blank、png_scale 以及
SVG/PNG/PDF 的轻量格式检查结果。复杂图面仍需按 quality-checklist.md 人工确认。

优先级：
1. drawio CLI（drawio-desktop 命令行模式）
2. 浏览器或桌面应用手动导出
3. 仅交付 .drawio（无法导出时）

用法：
    python scripts/export_drawio.py case.drawio
    python scripts/export_drawio.py case.drawio --format svg,png
    python scripts/export_drawio.py case.drawio --format png --png-scale 3
    python scripts/export_drawio.py cases/ --recursive
    python scripts/export_drawio.py case.drawio --in-place
"""
import argparse
from datetime import datetime
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

SUPPORTED_FORMATS = ("svg", "png", "pdf")
SKILL_ROOT = Path(__file__).resolve().parents[1]
KNOWN_DRAWIO_PATHS = (
    "/Applications/draw.io.app/Contents/MacOS/draw.io",
    "/Applications/diagrams.net.app/Contents/MacOS/diagrams.net",
)


def detect_drawio() -> str | None:
    """检测可用的 drawio 导出器，返回命令名或 None。"""
    for cmd in ("drawio", "draw.io", "drawio-desktop", "drawio-batch"):
        if shutil.which(cmd):
            return cmd
    for path in KNOWN_DRAWIO_PATHS:
        if Path(path).exists():
            return path
    return None


def inspect_export(path: Path, fmt: str, size: int) -> dict:
    result = {
        "size_bytes": size,
        "image_blank": size < 200,
        "manual_visual_check_required": True,
    }
    if fmt == "svg":
        text = path.read_text(encoding="utf-8", errors="ignore")
        result["svg_root_ok"] = "<svg" in text[:500].lower()
        match = re.search(
            r"viewBox=[\"']\s*[-0-9.]+\s+[-0-9.]+\s+([0-9.]+)\s+([0-9.]+)",
            text,
            re.IGNORECASE,
        )
        result["svg_viewbox_ok"] = bool(match and float(match.group(1)) > 0 and float(match.group(2)) > 0)
    elif fmt == "png":
        result["png_signature_ok"] = path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    elif fmt == "pdf":
        result["pdf_signature_ok"] = path.read_bytes().startswith(b"%PDF")
    return result


def safe_output_name(src: Path, fmt: str) -> str:
    try:
        rel = src.resolve().relative_to(SKILL_ROOT)
    except ValueError:
        rel = Path(src.name)
    stem = "__".join(rel.with_suffix("").parts)
    return f"{stem}.{fmt}"


def copy_drawio_source(src: Path, output_dir: Path | None) -> dict:
    if output_dir is None:
        return {
            "ok": True,
            "copied": False,
            "path": str(src),
            "message": "--in-place 模式下 .drawio 源文件保留在原目录",
        }
    out_path = output_dir / safe_output_name(src, "drawio")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        same_file = src.resolve() == out_path.resolve()
    except FileNotFoundError:
        same_file = False
    if not same_file:
        shutil.copy2(src, out_path)
    return {
        "ok": out_path.exists(),
        "copied": not same_file,
        "path": str(out_path),
        "size_bytes": out_path.stat().st_size if out_path.exists() else 0,
    }


def export_one(
    drawio_cmd: str,
    src: Path,
    fmt: str,
    output_dir: Path | None,
    png_scale: float,
) -> dict:
    out_path = output_dir / safe_output_name(src, fmt) if output_dir else src.with_suffix(f".{fmt}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [drawio_cmd, "--export", "--format", fmt, "--output", str(out_path), str(src)]
    if fmt == "png":
        cmd[-1:-1] = ["--scale", str(png_scale)]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120
        )
    except subprocess.TimeoutExpired:
        return {"format": fmt, "ok": False, "error": "导出超时"}
    except FileNotFoundError:
        return {"format": fmt, "ok": False, "error": f"命令未找到: {drawio_cmd}"}

    if result.returncode != 0:
        return {
            "format": fmt,
            "ok": False,
            "error": result.stderr.strip() or f"退出码 {result.returncode}",
        }

    if not out_path.exists():
        return {"format": fmt, "ok": False, "error": "导出后未找到输出文件"}

    size = out_path.stat().st_size
    report = {
        "format": fmt,
        "ok": True,
        "path": str(out_path),
        **inspect_export(out_path, fmt, size),
    }
    if fmt == "png":
        report["png_scale"] = png_scale
    return report


def export_file(src: Path, formats: list, output_dir: Path | None, png_scale: float) -> dict:
    source = copy_drawio_source(src, output_dir)
    cmd = detect_drawio()
    if cmd is None:
        return {
            "file": str(src),
            "source_drawio": source,
            "drawio_cmd": None,
            "fallback": "no_drawio_cli",
            "message": "未检测到 drawio CLI；已尽量保留 .drawio 源文件，可安装 draw.io/diagrams.net 桌面版或使用浏览器手动导出图片",
            "results": [],
        }

    results = [export_one(cmd, src, fmt, output_dir, png_scale) for fmt in formats]
    all_ok = source["ok"] and all(r["ok"] for r in results)
    return {
        "file": str(src),
        "source_drawio": source,
        "drawio_cmd": cmd,
        "fallback": None,
        "all_ok": all_ok,
        "results": results,
    }


def collect_files(targets: list, recursive: bool) -> list:
    files = []
    for t in targets:
        p = Path(t)
        if p.is_file():
            files.append(p)
        elif p.is_dir():
            it = p.rglob("*.drawio") if recursive else p.glob("*.drawio")
            files.extend(sorted(it))
    return files


def resolve_output_dir(args: argparse.Namespace) -> Path | None:
    if args.in_place:
        return None
    if args.output_dir:
        path = Path(args.output_dir)
    else:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = Path(args.archive_dir) / timestamp
    if not path.is_absolute():
        path = SKILL_ROOT / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_report_path(args: argparse.Namespace, output_dir: Path | None) -> Path:
    if args.report:
        path = Path(args.report)
        if not path.is_absolute():
            path = SKILL_ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    if output_dir:
        return output_dir / "export-report.json"
    return Path("export-report.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Legal Visualization drawio 批量导出")
    parser.add_argument("paths", nargs="+", help=".drawio 文件或目录")
    parser.add_argument(
        "--recursive", "-r", action="store_true", help="目录递归查找"
    )
    parser.add_argument(
        "--format",
        default="svg,png",
        help=f"图片导出格式，逗号分隔，可选 {SUPPORTED_FORMATS}；.drawio 源文件始终保留，默认 svg,png",
    )
    parser.add_argument(
        "--png-scale",
        type=float,
        default=2.0,
        help="PNG 导出倍率，默认 2.0；需要更高清时可设为 3 或 4",
    )
    parser.add_argument(
        "--report",
        default=None,
        help="报告输出路径（默认跟随 archive/<timestamp>/export-report.json；--in-place 时为当前目录 export-report.json）",
    )
    parser.add_argument(
        "--archive-dir",
        default="archive",
        help="归档根目录（默认 legal-visualization/archive）",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="指定导出目录；如不指定且未使用 --in-place，则写入 archive/<timestamp>/",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="导出到 .drawio 同目录，兼容旧行为",
    )
    parser.add_argument(
        "--json", action="store_true", help="同时把报告输出到 stdout"
    )
    args = parser.parse_args()

    formats = [f.strip() for f in args.format.split(",") if f.strip()]
    bad = [f for f in formats if f not in SUPPORTED_FORMATS]
    if bad:
        print(f"error: 不支持的格式 {bad}，可选 {SUPPORTED_FORMATS}", file=sys.stderr)
        return 2
    if args.png_scale <= 0:
        print("error: --png-scale 必须大于 0", file=sys.stderr)
        return 2

    files = collect_files(args.paths, args.recursive)
    if not files:
        print("error: 没有找到 .drawio 文件", file=sys.stderr)
        return 2

    output_dir = resolve_output_dir(args)
    report_path = resolve_report_path(args, output_dir)
    reports = [export_file(f, formats, output_dir, args.png_scale) for f in files]
    summary = {
        "total": len(reports),
        "all_ok": all(r.get("all_ok") for r in reports),
        "drawio_cmd": detect_drawio(),
        "output_dir": str(output_dir) if output_dir else None,
        "report_path": str(report_path),
        "png_scale": args.png_scale if "png" in formats else None,
        "reports": reports,
    }

    report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"drawio CLI: {summary['drawio_cmd'] or '未检测到'}")
        if output_dir:
            print(f"输出目录: {output_dir}")
        print(f"导出 {summary['total']} 个文件")
        for r in reports:
            status = "OK" if r.get("all_ok") else ("FALLBACK" if r.get("fallback") else "FAIL")
            print(f"\n[{status}] {r['file']}")
            source = r.get("source_drawio")
            if source and source.get("ok"):
                action = "复制" if source.get("copied") else "保留"
                print(f"  ✓ drawio 源文件已{action}: {source['path']}")
            if r.get("fallback"):
                print(f"  ! {r['message']}")
                continue
            for res in r["results"]:
                if res["ok"]:
                    print(f"  ✓ {res['format']} -> {res['path']} ({res['size_bytes']} bytes)")
                else:
                    print(f"  ✗ {res['format']} 失败: {res['error']}")
        print(f"\n报告已写入: {report_path}")

    return 0 if summary["all_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
