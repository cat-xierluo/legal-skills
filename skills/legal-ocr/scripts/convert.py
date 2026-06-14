#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = [
#   "httpx>=0.27.0",
#   "pypdfium2>=4.30.0",
# ]
# ///

"""legal-ocr 统一入口：通用 OCR 自动路由到 PaddleOCR 或 MinerU，输出 Markdown 与 archive。"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import traceback
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from base import BackendResult, ConvertOptions  # noqa: E402
from mineru_ocr import MinerUBackend  # noqa: E402
from paddle_ocr import PaddleOCRBackend  # noqa: E402
from common import (  # noqa: E402
    PADDLE_LOCAL_SUFFIXES,
    SourceInfo,
    build_source_info,
    first_non_empty,
    get_skill_root,
    load_env,
    parse_bool,
    resolve_images_dir,
    resolve_output_markdown_path,
    sanitize_name,
    sha256_of_file,
)
from pdf_tools import get_pdf_page_count  # noqa: E402
from basic_postprocess import run_basic_postprocess  # noqa: E402
from legal_terms import detect_legal_context, run_legal_terms_postprocess  # noqa: E402
from linebreaks import run_linebreak_postprocess  # noqa: E402
from router import RouteDecision, choose_backend  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="将 PDF、图片、Office 文档或 URL 转换为 Markdown，并在法律材料中自动启用保守增强"
    )
    parser.add_argument("input", help='本地文件、远程 URL，或 "checktoken"')
    parser.add_argument("--backend", choices=["auto", "paddle", "mineru"], default=None)
    parser.add_argument("--output", help="输出 Markdown 路径；如果不是 .md，则按目录处理")
    parser.add_argument("--pages", help='页码范围，例如 "1-20" 或 "1-5,8,10-12"')
    parser.add_argument("--archive-name", help="自定义 archive 目录名后缀，默认使用输入文件名")
    parser.add_argument("--no-archive", action="store_true", help="不写入 archive，仅输出 Markdown")
    parser.add_argument("--no-post-process", action="store_true", help="跳过全部后处理")
    parser.add_argument("--no-legal-terms", action="store_true", help="跳过法律术语优化")
    parser.add_argument(
        "--legal-terms",
        choices=["auto", "always", "never"],
        help="法律术语优化模式；auto 仅在检测到法律材料时启用",
    )
    parser.add_argument("--no-line-merge", action="store_true", help="跳过 OCR 硬换行整理")
    parser.add_argument("--model", choices=["pipeline", "vlm"], help="MinerU Token API 模型")
    parser.add_argument(
        "--paddle-model",
        choices=["PP-OCRv5", "PaddleOCR-VL-1.5"],
        help="PaddleOCR 异步任务模型；Markdown 输出建议 PaddleOCR-VL-1.5",
    )
    parser.add_argument(
        "--paddle-api-protocol",
        choices=["auto", "sync", "async"],
        help="PaddleOCR API 协议；layout-parsing 用 sync，/api/v2/ocr/jobs 用 async",
    )
    parser.add_argument("--paddle-api-extra-json", help="额外 PaddleOCR optionalPayload JSON 文件")
    return parser.parse_args(argv)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def copytree_if_exists(source: Path | None, target: Path) -> None:
    if source and source.exists():
        shutil.copytree(source, target, dirs_exist_ok=True)


def build_source(raw_input: str) -> SourceInfo:
    source = build_source_info(raw_input)
    if source.path and source.suffix == ".pdf":
        source = replace(source, page_count=get_pdf_page_count(source.path))
    return source


def should_postprocess(env: dict[str, str], no_post_process: bool) -> bool:
    if no_post_process:
        return False
    return parse_bool(env.get("LEGAL_OCR_POST_PROCESS"), default=True)


def legal_terms_mode(env: dict[str, str], no_legal_terms: bool, cli_value: str | None) -> str:
    if no_legal_terms:
        return "never"
    configured = (cli_value or env.get("LEGAL_OCR_LEGAL_TERMS") or "auto").strip().lower()
    aliases = {
        "true": "always",
        "1": "always",
        "yes": "always",
        "on": "always",
        "always": "always",
        "force": "always",
        "false": "never",
        "0": "never",
        "no": "never",
        "off": "never",
        "never": "never",
        "auto": "auto",
    }
    if configured not in aliases:
        raise ValueError("LEGAL_OCR_LEGAL_TERMS 仅支持 auto/true/false，或命令行 auto/always/never")
    return aliases[configured]


def should_line_merge(env: dict[str, str], no_line_merge: bool) -> bool:
    if no_line_merge:
        return False
    return parse_bool(env.get("LEGAL_OCR_LINE_MERGE"), default=True)


def make_backend(name: str, env: dict[str, str]) -> Any:
    if name == "paddle":
        return PaddleOCRBackend(env)
    if name == "mineru":
        return MinerUBackend(env)
    raise ValueError(f"未知后端：{name}")


def source_json(source: SourceInfo) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "raw": source.raw,
        "type": source.source_type,
        "name": source.file_name,
        "suffix": source.suffix,
        "page_count": source.page_count,
    }
    if source.path:
        payload["path"] = str(source.path)
        payload["sha256"] = sha256_of_file(source.path)
        payload["size_bytes"] = source.size_bytes
    return payload


def build_archive(
    *,
    source: SourceInfo,
    archive_name: str,
    output_md_path: Path,
    output_images_dir: Path,
    raw_markdown: str,
    result_json: dict[str, Any],
    metadata: dict[str, Any],
    backend_result_dir: Path | None,
) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_root = get_skill_root() / "archive" / f"{timestamp}_{sanitize_name(archive_name)}"
    output_dir = archive_root / "output"
    batches_dir = archive_root / "batches"
    backend_dir = archive_root / "backend_result"

    output_dir.mkdir(parents=True, exist_ok=True)

    shutil.copy2(output_md_path, output_dir / "result.md")
    write_text(output_dir / "result_raw.md", raw_markdown)
    write_json(output_dir / "result.json", result_json)

    if output_images_dir.exists():
        shutil.copytree(output_images_dir, output_dir / "images", dirs_exist_ok=True)

    if backend_result_dir and backend_result_dir.exists():
        shutil.copytree(backend_result_dir, backend_dir, dirs_exist_ok=True)
        batch_files = sorted(backend_result_dir.glob("batch_*.json"))
        if batch_files:
            batches_dir.mkdir(parents=True, exist_ok=True)
            for batch_file in batch_files:
                shutil.copy2(batch_file, batches_dir / batch_file.name)

    write_json(archive_root / "metadata.json", metadata)
    if metadata.get("postprocess_log"):
        write_json(archive_root / "postprocess_log.json", metadata["postprocess_log"])
    return archive_root


def copy_attempt_assets(attempt_assets_dir: Path, output_images_dir: Path) -> bool:
    if not attempt_assets_dir.exists() or not any(attempt_assets_dir.iterdir()):
        return False
    if output_images_dir.exists():
        shutil.rmtree(output_images_dir)
    shutil.copytree(attempt_assets_dir, output_images_dir)
    return True


def update_image_paths(images: list[dict[str, str]], output_images_dir: Path) -> None:
    for image in images:
        filename = image.get("filename")
        if filename:
            image["path"] = str(output_images_dir / filename)


def build_result_payload(
    *,
    source: SourceInfo,
    backend_result: BackendResult,
    route: RouteDecision,
    attempts: list[dict[str, str]],
    raw_markdown: str,
    final_markdown: str,
    postprocess_log: list[dict[str, str]],
    postprocess_enabled: bool,
    legal_context: dict[str, Any],
) -> dict[str, Any]:
    metadata = backend_result.metadata or {}
    return {
        "ok": True,
        "source": source_json(source),
        "backend": {
            "name": backend_result.backend,
            "mode": backend_result.mode,
            "provider": backend_result.provider,
        },
        "route": {
            "preferred": route.preferred,
            "candidates": route.candidates,
            "reason": route.reason,
            "notes": route.notes,
            "attempts": attempts,
        },
        "processing": metadata.get("processing", {}),
        "text": final_markdown,
        "raw_text": raw_markdown,
        "images": backend_result.images,
        "batches": backend_result.batches,
        "postprocess": {
            "enabled": postprocess_enabled,
            "log_count": len(postprocess_log),
            "legal_context": legal_context,
        },
    }


def classify_backend_error(error: Exception) -> str:
    message = str(error)
    lowered = message.lower()

    quota_terms = (
        "429",
        "quota",
        "rate limit",
        "rate-limit",
        "rate_limited",
        "too many requests",
        "limit exceeded",
        "insufficient",
        "配额",
        "额度",
        "余额",
        "用量",
        "频率",
        "资源包",
        "点数",
    )
    if any(term in lowered or term in message for term in quota_terms):
        return "quota_or_rate_limit"

    auth_terms = ("401", "403", "unauthorized", "forbidden", "access denied", "鉴权", "认证失败")
    if any(term in lowered or term in message for term in auth_terms):
        return "auth"

    if "免登录轻量接口限制" in message:
        return "light_limit"

    unsupported_terms = ("unsupported", "不支持", "仅由", "只能走", "暂不支持")
    if any(term in lowered or term in message for term in unsupported_terms):
        return "unsupported"

    timeout_terms = ("timeout", "timed out", "超时")
    if any(term in lowered or term in message for term in timeout_terms):
        return "timeout"

    network_terms = ("network", "connection", "connect", "网络", "连接")
    if any(term in lowered or term in message for term in network_terms):
        return "network"

    return "error"


def run_checktoken(env: dict[str, str]) -> int:
    print("legal-ocr 配置自检")
    print("===============================================")
    try:
        mineru = MinerUBackend(env)
        print(f"MinerU: {mineru.verify_token()}")
    except Exception as error:  # noqa: BLE001
        print(f"MinerU: {error}")

    try:
        PaddleOCRBackend(env)
        print("PaddleOCR: 已检测到必要配置。")
    except Exception as error:  # noqa: BLE001
        print(f"PaddleOCR: {error}")
    return 0


def convert_once(
    *,
    backend_name: str,
    env: dict[str, str],
    source: SourceInfo,
    options: ConvertOptions,
    temp_root: Path,
) -> tuple[BackendResult, Path]:
    backend = make_backend(backend_name, env)
    work_dir = temp_root / backend_name
    assets_dir = temp_root / f"{backend_name}_assets"
    work_dir.mkdir(parents=True, exist_ok=True)
    return backend.convert(source, options, work_dir, assets_dir), assets_dir


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    env = load_env()
    if args.paddle_model:
        env["PADDLEOCR_MODEL"] = args.paddle_model
    if args.paddle_api_protocol:
        env["PADDLEOCR_API_PROTOCOL"] = args.paddle_api_protocol
    if args.paddle_api_extra_json:
        env["PADDLEOCR_API_EXTRA_JSON"] = args.paddle_api_extra_json

    if args.input in {"checktoken", "verify-token", "--verify-token"}:
        return run_checktoken(env)

    source = build_source(args.input)
    configured_backend = args.backend or env.get("LEGAL_OCR_BACKEND", "auto")
    route = choose_backend(source, env, configured_backend)
    output_md_path = resolve_output_markdown_path(source, args.output)
    output_images_dir = resolve_images_dir(output_md_path)
    archive_name = args.archive_name or source.base_name
    options = ConvertOptions(
        pages=args.pages,
        model=args.model,
        paddle_model=args.paddle_model,
        log_level=first_non_empty(env, "LEGAL_OCR_LOG_LEVEL", "PADDLEOCR_LOG_LEVEL", "MINERU_LOG_LEVEL") or "medium",
    )
    try:
        postprocess_enabled = should_postprocess(env, args.no_post_process)
        configured_legal_terms_mode = (
            legal_terms_mode(env, args.no_legal_terms, args.legal_terms) if postprocess_enabled else "disabled"
        )
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2

    temp_root = Path(tempfile.mkdtemp(prefix="legal_ocr_"))
    attempts: list[dict[str, str]] = []
    try:
        last_error: Exception | None = None
        for attempt_index, backend_name in enumerate(route.candidates):
            try:
                backend_result, attempt_assets_dir = convert_once(
                    backend_name=backend_name,
                    env=env,
                    source=source,
                    options=options,
                    temp_root=temp_root,
                )
                attempts.append({"backend": backend_name, "status": "success"})
                raw_markdown = backend_result.markdown.strip()
                if postprocess_enabled:
                    working_markdown = raw_markdown
                    postprocess_log: list[dict[str, str]] = []
                    mode = configured_legal_terms_mode
                    legal_context = {
                        "mode": mode,
                        "enabled": False,
                        "detection": None,
                    }
                    if mode == "auto":
                        detection = detect_legal_context(working_markdown, source_name=source.file_name)
                        legal_context["detection"] = detection
                        legal_context["enabled"] = bool(detection["is_legal"])
                        if not detection["is_legal"]:
                            postprocess_log.append(
                                {
                                    "action": "legal_terms_skip",
                                    "category": "legal_context_auto",
                                    "description": "未检测到足够法律文书信号，跳过法律术语优化",
                                    "score": str(detection["score"]),
                                }
                            )
                    elif mode == "always":
                        legal_context["enabled"] = True

                    if legal_context["enabled"]:
                        legal_terms_result = run_legal_terms_postprocess(
                            working_markdown,
                            custom_terms_path=env.get("LEGAL_OCR_CUSTOM_TERMS_PATH"),
                        )
                        working_markdown = legal_terms_result.text
                        postprocess_log.extend(legal_terms_result.log)

                    if should_line_merge(env, args.no_line_merge):
                        linebreak_result = run_linebreak_postprocess(working_markdown)
                        working_markdown = linebreak_result.text
                        postprocess_log.extend(linebreak_result.log)

                    postprocessed = run_basic_postprocess(working_markdown)
                    final_markdown = postprocessed.text
                    postprocess_log.extend(postprocessed.log)
                else:
                    final_markdown = raw_markdown
                    postprocess_log = []
                    legal_context = {
                        "mode": "disabled",
                        "enabled": False,
                        "detection": None,
                    }

                write_text(output_md_path, final_markdown)
                if copy_attempt_assets(attempt_assets_dir, output_images_dir):
                    update_image_paths(backend_result.images, output_images_dir)

                result_json = build_result_payload(
                    source=source,
                    backend_result=backend_result,
                    route=route,
                    attempts=attempts,
                    raw_markdown=raw_markdown,
                    final_markdown=final_markdown,
                    postprocess_log=postprocess_log,
                    postprocess_enabled=postprocess_enabled,
                    legal_context=legal_context,
                )
                metadata = {
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                    "source": source_json(source),
                    "backend": result_json["backend"],
                    "route": result_json["route"],
                    "output_markdown": str(output_md_path),
                    "image_output_dir": str(output_images_dir) if output_images_dir.exists() else None,
                    "postprocess_enabled": postprocess_enabled,
                    "legal_context": result_json["postprocess"]["legal_context"],
                    "postprocess_log": postprocess_log,
                    "backend_metadata": backend_result.metadata,
                }

                archive_path: Path | None = None
                if not args.no_archive:
                    archive_path = build_archive(
                        source=source,
                        archive_name=archive_name,
                        output_md_path=output_md_path,
                        output_images_dir=output_images_dir,
                        raw_markdown=raw_markdown,
                        result_json=result_json,
                        metadata=metadata,
                        backend_result_dir=backend_result.backend_result_dir,
                    )

                print("转换完成")
                print(f"Markdown: {output_md_path}")
                if output_images_dir.exists():
                    print(f"图片目录: {output_images_dir}")
                if archive_path:
                    print(f"Archive: {archive_path}")
                print(f"后端: {backend_result.backend} ({backend_result.mode})")
                # 输出实际使用的模型名，供上游 run_ocr.py 解析
                _model = (backend_result.metadata or {}).get("config", {}).get("model")
                if _model:
                    print(f"OCR_MODEL: {_model}")
                return 0
            except Exception as error:  # noqa: BLE001
                category = classify_backend_error(error)
                has_next_backend = attempt_index < len(route.candidates) - 1
                attempt: dict[str, str] = {
                    "backend": backend_name,
                    "status": "failed",
                    "category": category,
                    "error": str(error),
                }
                if route.fallback_allowed and has_next_backend:
                    attempt["fallback"] = "next_backend"
                attempts.append(attempt)
                last_error = error
                if not route.fallback_allowed or not has_next_backend:
                    break

        print("转换失败", file=sys.stderr)
        for attempt in attempts:
            detail = f"- {attempt['backend']}: {attempt['status']}"
            if "error" in attempt:
                detail += f" - {attempt['error']}"
            print(detail, file=sys.stderr)
        if last_error:
            # 2026-06-14 加诊断性 logging:
            # 旧实现 `print(f"最后错误:{last_error}")` 把异常 str() 化掉,丢了 type 和 traceback;
            # 上游 run_ocr.py:326 只抓 stderr 最后一行,导致 segments.last_error 短得无法定位真因
            # (例:`Invalid port: ':1]'` 是 httpx.InvalidURL 的 message,但看不出哪个 url 哪个 client 抛的)。
            # 现在最后一行带 type 名,traceback 在 stderr 全文里供 archive / cron 日志回溯。
            tb_lines = traceback.format_exception(type(last_error), last_error, last_error.__traceback__)
            print("最后错误 traceback:", file=sys.stderr)
            for ln in tb_lines:
                print(ln, file=sys.stderr, end="")
            # 末行(保留旧前缀让上游 splitlines()[-1] 兼容,但补上 type 名定位异常类)
            print(f"最后错误:{type(last_error).__name__}: {last_error}", file=sys.stderr)
        return 1
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    # 2026-06-14 入口级 catch:之前 1.4.1 加的 try/except 在 main() 内 backend 循环里,
    # 但有些异常更早(如 PaddleOCRBackend.__init__ / MinerUBackend.__init__ 调
    # httpx.URL / httpx.Client 校验,或 route 解析阶段)就抛出,绕过内部 catch。
    # 在入口层兜底 catch BaseException + 立即 traceback.print_exc 到 stderr,
    # 保证不管哪行抛错,完整 stack 必进 stderr,上游 run_ocr.py 扩信道后能完整读到。
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException as _entry_exc:
        print(f"convert.py 入口异常:{type(_entry_exc).__name__}: {_entry_exc}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        raise SystemExit(1)
