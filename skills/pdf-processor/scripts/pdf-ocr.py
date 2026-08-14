#!/usr/bin/env python3
"""
PDF OCR 工具（统一入口）

目标：
- 保留稳定本地兜底路径：ocrmypdf
- 兼容外部 PaddleOCR API 后端（官方协议优先，旧协议兼容）
- 新增外部 MinerU API 后端（异步任务 + ZIP 结果解析 + 本地叠层）
- 提供 auto 后端：默认按 Paddle/MinerU 顺序尝试已配置 API，失败后回退本地
- 提供 --local-only：对不允许外传的材料强制只用本地 ocrmypdf
- 本地 Paddle 双层实现仅保留为内部历史实现，不再作为公开 CLI 选项

模块拆分：
- pdf_runtime.py      : 环境变量、依赖提示、HTTP 工具
- pdf_ocr_layered.py   : 双层叠层核心、OCR 结果解析、CJK 归一化
- pdf_ocr_mineru.py    : MinerU API 后端
- pdf_ocr_paddle_api.py: Paddle API 后端
- pdf_ocr_paddle_local.py: 历史保留的本地 Paddle 双层后端
- pdf-ocr.py (本文件)  : 入口、argparse、ocrmypdf、auto 策略
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from pdf_runtime import (
    DEFAULT_MINERU_API_BASE_ENV,
    DEFAULT_MINERU_API_TOKEN_ENV,
    DEFAULT_MINERU_USER_TOKEN_ENV,
    DEFAULT_PADDLE_API_ENDPOINT_ENV,
    DEFAULT_PADDLE_API_KEY_ENV,
    apply_api_env_aliases,
    load_env_file,
    print_dependency_help,
    strip_quoted,
)

from pdf_ocr_mineru import run_mineru_api_backend

from pdf_ocr_paddle_api import SUPPORTED_PADDLE_MODELS, run_paddle_api_backend


# ---------- 常量 ----------

MODE_TO_FLAG = {
    "skip": "--skip-text",
    "redo": "--redo-ocr",
    "force": "--force-ocr",
}

DEFAULT_OCR_API_ORDER_ENV = "OCR_API_ORDER"
DEFAULT_ENV_FILE_PATH = str(Path(__file__).resolve().parent.parent / "config" / ".env")


# ---------- CLI 工具 ----------

def _split_csv_tokens(raw: str) -> list[str]:
    if not raw:
        return []
    parts = re.split(r"[,\s;|]+", raw.strip())
    return [p.strip() for p in parts if p.strip()]


def normalize_provider_name(raw: str) -> str | None:
    name = (raw or "").strip().lower()
    mapping = {
        "mineru": "mineru",
        "mineru_api": "mineru",
        "miner-u": "mineru",
        "paddle": "paddle",
        "paddle_api": "paddle",
        "paddleocr": "paddle",
        "paddle_ocr": "paddle",
    }
    return mapping.get(name)


def parse_api_order(raw: str) -> list[str]:
    providers: list[str] = []
    for token in _split_csv_tokens(raw):
        name = normalize_provider_name(token)
        if not name:
            continue
        if name not in providers:
            providers.append(name)
    return providers


def extract_api_order_from_env_file(env_file: str) -> list[str]:
    """
    从 .env 文件中提取 API 顺序。
    优先读取 OCR_API_ORDER；若未设置，则按"关键配置项出现顺序"推断。
    """
    p = Path(env_file).expanduser()
    if not p.exists():
        return []

    ordered: list[str] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        if raw.startswith("export "):
            raw = raw[len("export "):].strip()
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        value = strip_quoted(value)
        if not key:
            continue
        if key == DEFAULT_OCR_API_ORDER_ENV:
            explicit = parse_api_order(value)
            if explicit:
                return explicit

        inferred: str | None = None
        if key in {"MINERU_API_BASE", "MINERU_API_BASE_URL", "MINERU_BASE_URL", "MINERU_API_ENDPOINT"}:
            inferred = "mineru"
        elif key in {"PADDLE_OCR_API_ENDPOINT", "API_URL"}:
            inferred = "paddle"

        if inferred and inferred not in ordered:
            ordered.append(inferred)
    return ordered


# ---------- ocrmypdf 后端 ----------

def build_ocrmypdf_command(args) -> list[str]:
    """构建 ocrmypdf 命令。"""
    cmd = [
        "ocrmypdf",
        "--output-type", args.output_type,
        "--language", args.language,
        "--optimize", str(args.optimize),
        "--skip-big", str(args.skip_big),
        "--tesseract-timeout", str(args.tesseract_timeout),
        MODE_TO_FLAG[args.mode],
    ]

    if args.jobs:
        cmd += ["--jobs", str(args.jobs)]

    if args.sidecar:
        cmd += ["--sidecar", args.sidecar]

    if args.fast_web_view is not None:
        cmd += ["--fast-web-view", str(args.fast_web_view)]

    # 如果输入已做过预处理，则避免重复旋转与倾斜矫正
    if not args.preprocessed:
        if not args.no_rotate_pages:
            cmd.append("--rotate-pages")
        # ocrmypdf 限制：--redo-ocr 与 --deskew/--clean 不兼容
        if args.mode != "redo":
            if not args.no_deskew:
                cmd.append("--deskew")
            if not args.no_clean:
                cmd.append("--clean")

    cmd += [args.input, args.output]
    return cmd


def ensure_ocrmypdf_available() -> bool:
    """检查 ocrmypdf 是否可用。"""
    if shutil.which("ocrmypdf") is None:
        print_dependency_help(
            "本地 ocrmypdf 后端",
            missing_python=["ocrmypdf"],
            missing_system=["tesseract", "tesseract-chi_sim"],
            install_commands=[
                "pip install ocrmypdf",
                "macOS: brew install tesseract tesseract-lang",
                "Linux: sudo apt-get install tesseract-ocr tesseract-ocr-chi-sim",
            ],
            extra_notes=[
                "安装完成后请确认 `ocrmypdf` 命令已在 PATH 中可用。",
            ],
        )
        return False
    return True


def run_local_ocrmypdf_backend(args):
    """执行本地 ocrmypdf 后端。"""
    if not ensure_ocrmypdf_available():
        raise RuntimeError("本地 ocrmypdf 不可用")

    cmd = build_ocrmypdf_command(args)

    if not args.quiet:
        print("\n执行命令:")
        print(" ".join(cmd))
        print()

    if args.dry_run:
        print("[DRY-RUN] 本地 ocrmypdf 命令已输出，未实际执行。")
        args.backend_used = "local_ocrmypdf"
        return

    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise RuntimeError(f"ocrmypdf 执行失败（退出码 {result.returncode}）")

    # 保留原文件时间戳
    try:
        shutil.copystat(args.input, args.output)
    except Exception:
        pass

    args.backend_used = "local_ocrmypdf"


# ---------- JSON 加载 ----------

def load_json_file(path: str | None) -> dict:
    """读取额外 JSON 配置。"""
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        raise ValueError(f"额外 JSON 文件不存在: {path}")
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("额外 JSON 文件必须是对象（dict）")
    return data


def _cli_arg_present(flag: str) -> bool:
    """判断某个 CLI 参数是否由用户显式传入。"""
    for arg in sys.argv[1:]:
        if arg == flag or arg.startswith(flag + "="):
            return True
    return False


# ---------- Auto 后端策略 ----------

def resolve_external_api_order(args) -> list[str]:
    """
    解析外部 API 优先级：
    1) CLI `--api-order`
    2) 环境变量 `OCR_API_ORDER`
    3) .env 文件中的配置顺序
    4) 默认顺序（paddle, mineru）
    """
    if args.api_order:
        ordered = parse_api_order(args.api_order)
        if ordered:
            return ordered

    env_order = parse_api_order(os.getenv(DEFAULT_OCR_API_ORDER_ENV, ""))
    if env_order:
        return env_order

    if not args.no_env_file:
        file_order = extract_api_order_from_env_file(args.env_file)
        if file_order:
            return file_order

    return ["paddle", "mineru"]


def run_auto_backend(args):
    """
    自动后端策略：
    1) 默认按 paddle/mineru 顺序尝试已配置服务
    2) --local-only 时不调用任何外部 API
    3) 外部服务不可用时回退本地 ocrmypdf
    """
    api_errs = []

    external_candidates: list[str] = []
    for provider in args.external_api_order:
        if provider == "mineru" and args.mineru_api_base:
            external_candidates.append("mineru")
        elif provider == "paddle" and args.paddle_api_endpoint:
            external_candidates.append("paddle")

    configured_external = bool(external_candidates)
    if external_candidates and getattr(args, "local_only", False):
        if not args.quiet:
            print(
                "提示: 已启用 --local-only；跳过已配置的外部 OCR API。"
            )
        external_candidates = []

    if external_candidates:
        prev_no_fallback = args.no_paddle_fallback_local
        args.no_paddle_fallback_local = True
        try:
            for provider in external_candidates:
                try:
                    if provider == "mineru":
                        run_mineru_api_backend(args)
                    else:
                        run_paddle_api_backend(args)
                    return
                except Exception as e:
                    api_errs.append(f"{provider}:{e}")
                    if not args.quiet:
                        print(f"警告: 外部 API({provider}) 不可用，尝试下一个。原因: {e}")
        finally:
            args.no_paddle_fallback_local = prev_no_fallback

        try:
            run_local_ocrmypdf_backend(args)
            return
        except Exception as e:
            raise RuntimeError(
                "auto 后端失败（API 优先路径）。"
                f"api_errors={api_errs}; ocrmypdf_error={e}"
            )

    if not args.quiet:
        if not configured_external:
            print(
                "提示: 当前未配置外部 OCR API，将使用本地 ocrmypdf。"
            )
        elif getattr(args, "local_only", False):
            print("提示: 当前强制使用本地 ocrmypdf。")
        else:
            print("提示: 外部 API 均不可用，回退本地 ocrmypdf。")

    try:
        run_local_ocrmypdf_backend(args)
    except Exception as e:
        raise RuntimeError(
            "auto 后端全部失败。"
            f"api_errors={api_errs}; ocrmypdf_error={e}"
        )


# ---------- 公共入口函数 ----------

def run_ocr(**kwargs):
    """
    OCR 公共入口函数。

    接受与 argparse 选项同名的关键字参数，直接调用对应后端。
    供 pdf-preprocess-ocr.py 等外部模块直接调用，无需 subprocess。

    参数：
        input: 输入 PDF 文件路径
        output: 输出 PDF 文件路径
        backend: 后端选择 (auto/local_ocrmypdf/paddle_api/mineru_api；local_paddle_layered 为内部保留)
        mode: OCR 模式 (skip/redo/force)
        language: 语言参数
        output_type: 输出类型 (pdf/pdfa)
        optimize: 优化级别 (0-3)
        skip_big: 跳过大图阈值 (MP)
        tesseract_timeout: Tesseract 超时秒数
        jobs: 并行任务数
        sidecar: sidecar 文件路径
        fast_web_view: 线性化参数
        preprocessed: 是否已预处理
        no_rotate_pages: 禁用旋转
        no_deskew: 禁用倾斜矫正
        no_clean: 禁用去噪
        quiet: 安静模式
        dry_run: 仅输出命令
        env_file: .env 文件路径
        no_env_file: 禁用 .env
        api_order: 外部 API 顺序
        local_only: 强制不调用外部 API
        paddle_api_endpoint: Paddle API 地址
        paddle_api_endpoint_env: Paddle endpoint 环境变量名
        paddle_api_key_env: Paddle API Key 环境变量名
        paddle_api_timeout: Paddle API 超时
        paddle_api_retries: Paddle API 重试次数
        paddle_api_extra_json: Paddle 额外 JSON
        paddle_api_protocol: Paddle API 协议
        no_paddle_fallback_local: Paddle API 失败不回退
        mineru_api_base: MinerU API Base
        mineru_api_base_env: MinerU base 环境变量名
        mineru_api_token_env: MinerU Token 环境变量名
        mineru_user_token_env: MinerU User Token 环境变量名
        mineru_api_timeout: MinerU API 超时
        mineru_poll_interval: MinerU 轮询间隔
        mineru_poll_timeout: MinerU 轮询超时
        mineru_model_version: MinerU 模型版本
        mineru_language: MinerU 语言
        mineru_enable_formula: MinerU 启用公式
        mineru_enable_table: MinerU 启用表格
        mineru_api_extra_json: MinerU 额外 JSON
        paddle_lang: Paddle 语言
        paddle_profile: Paddle 档位
        paddle_long_doc_pages: Paddle 长文档阈值
        paddle_dpi: Paddle DPI
        paddle_det_limit_side_len: Paddle 检测边长限制
        paddle_det_model_name: Paddle 检测模型名
        paddle_rec_model_name: Paddle 识别模型名
        paddle_min_score: Paddle 最低分数
        paddle_skip_text_min_chars: Paddle 跳过文本最少字符
        paddle_textline_orientation: Paddle 文本行方向
        paddle_use_gpu: Paddle 使用 GPU
        no_paddle_cjk_space_normalize: 不归一化 CJK 空格
        keep_paddle_model_source_check: 保留模型源检查
        paddle_model_source: Paddle 模型源
    """
    import types

    args = types.SimpleNamespace(**kwargs)

    # 确保 paddle_dpi_user_set / paddle_det_limit_user_set 存在
    if not hasattr(args, "paddle_dpi_user_set"):
        args.paddle_dpi_user_set = kwargs.get("paddle_dpi") is not None
    if not hasattr(args, "paddle_det_limit_user_set"):
        args.paddle_det_limit_user_set = kwargs.get("paddle_det_limit_side_len") is not None

    # 设置默认值（与 argparse 保持一致）
    defaults = {
        "backend": "auto",
        "mode": "skip",
        "language": "chi_sim+eng",
        "output_type": "pdf",
        "optimize": 0,
        "skip_big": 50.0,
        "tesseract_timeout": 180,
        "jobs": None,
        "sidecar": None,
        "fast_web_view": None,
        "preprocessed": False,
        "no_rotate_pages": False,
        "no_deskew": False,
        "no_clean": False,
        "quiet": False,
        "dry_run": False,
        "env_file": DEFAULT_ENV_FILE_PATH,
        "no_env_file": False,
        "api_order": None,
        "local_only": False,
        "allow_external_upload": False,
        "archive_results": False,
        "paddle_model": "PP-OCRv6",
        "paddle_api_endpoint": None,
        "paddle_api_endpoint_env": DEFAULT_PADDLE_API_ENDPOINT_ENV,
        "paddle_api_key_env": DEFAULT_PADDLE_API_KEY_ENV,
        "paddle_api_timeout": 180,
        "paddle_api_retries": 1,
        "paddle_api_extra_json": None,
        "paddle_api_protocol": "auto",
        "no_paddle_fallback_local": False,
        "no_photo_correct": False,
        "paddle_vl_layout_detection": True,
        "paddle_vl_no_layout_detection": False,
        "paddle_vl_chart_recognition": False,
        "paddle_vl_doc_orientation": False,
        "paddle_vl_doc_unwarping": False,
        "paddle_vl_layout_shape_mode": "rect",
        "ocr_dump": None,
        "dump_and_pdf": False,
        "ocr_resume": None,
        "corrections_file": None,
        "actualtext": True,
        "no_actualtext": False,
        "layout_dump": None,
        "clean_text_output": None,
        "mineru_api_base": None,
        "mineru_api_base_env": DEFAULT_MINERU_API_BASE_ENV,
        "mineru_api_token_env": DEFAULT_MINERU_API_TOKEN_ENV,
        "mineru_user_token_env": DEFAULT_MINERU_USER_TOKEN_ENV,
        "mineru_api_timeout": 180,
        "mineru_poll_interval": 2,
        "mineru_poll_timeout": 1800,
        "mineru_model_version": "",
        "mineru_language": "",
        "mineru_enable_formula": False,
        "mineru_enable_table": False,
        "mineru_api_extra_json": None,
        "paddle_lang": "",
        "paddle_profile": "auto",
        "paddle_long_doc_pages": 60,
        "paddle_dpi": 300,
        "paddle_det_limit_side_len": 1536,
        "paddle_det_model_name": "",
        "paddle_rec_model_name": "",
        "paddle_min_score": 0.5,
        "paddle_skip_text_min_chars": 1,
        "paddle_textline_orientation": False,
        "paddle_use_gpu": False,
        "no_paddle_cjk_space_normalize": False,
        "keep_paddle_model_source_check": False,
        "paddle_model_source": None,
        "backend_used": None,
    }
    for key, default in defaults.items():
        if not hasattr(args, key) or getattr(args, key) is None:
            setattr(args, key, default)

    # 案件材料默认不在 Skill 目录或源文件旁生成 OCR 文本副本。
    if "no_archive" in kwargs:
        args.no_archive = bool(kwargs["no_archive"])
    else:
        args.no_archive = not bool(args.archive_results)

    # 加载环境变量
    if not args.no_env_file:
        load_env_file(args.env_file, quiet=args.quiet)
    apply_api_env_aliases()

    # 零参数自动化：允许通过环境变量提供 API endpoint
    if not args.paddle_api_endpoint:
        endpoint = os.getenv(args.paddle_api_endpoint_env, "").strip()
        args.paddle_api_endpoint = endpoint if endpoint else None
    if not args.mineru_api_base:
        mineru_base = os.getenv(args.mineru_api_base_env, "").strip()
        args.mineru_api_base = mineru_base if mineru_base else None
    args.external_api_order = resolve_external_api_order(args)

    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"输入文件不存在: {args.input}")

    # 默认输出：原文件同目录，添加 _OCR 后缀
    if not args.output:
        args.output = str(input_path.with_stem(input_path.stem + "_OCR"))

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if args.local_only and args.backend in {"paddle_api", "mineru_api"}:
        raise ValueError("--local-only 不能与显式外部 API 后端同时使用")

    if not args.quiet:
        print("=" * 60)
        print("PDF OCR")
        print("=" * 60)
        print(f"输入文件: {args.input}")
        print(f"输出文件: {args.output}")
        print(f"后端: {args.backend}")
        if args.backend == "auto":
            configured_api = [
                p for p in args.external_api_order
                if (p == "mineru" and args.mineru_api_base) or (p == "paddle" and args.paddle_api_endpoint)
            ]
            print(
                "auto策略: "
                + (
                    f"按顺序优先外部API({','.join(configured_api)})"
                    if configured_api and not args.local_only
                    else "已启用 local-only，强制本地 ocrmypdf"
                    if args.local_only
                    else "未配置外部API，当前使用本地 ocrmypdf"
                )
            )
        print(f"OCR 模式: {args.mode}")
        print(f"语言: {args.language}")
        print(f"输出类型: {args.output_type}")
        print(f"预处理状态: {'已预处理' if args.preprocessed else '未预处理'}")

    if args.backend == "auto":
        run_auto_backend(args)
    elif args.backend == "local_ocrmypdf":
        run_local_ocrmypdf_backend(args)
    elif args.backend == "paddle_api":
        run_paddle_api_backend(args)
    elif args.backend == "mineru_api":
        run_mineru_api_backend(args)
    elif args.backend == "local_paddle_layered":
        from pdf_ocr_paddle_local import run_local_paddle_layered_backend
        run_local_paddle_layered_backend(args, fallback_backend=run_local_ocrmypdf_backend)
    else:
        raise ValueError(f"未知 OCR 后端: {args.backend}")

    if not args.quiet:
        print("=" * 60)
        print("处理完成！")
        print(f"实际后端: {args.backend_used}")
        print(f"输出文件: {args.output}")
        print("=" * 60)


# ---------- CLI 入口 ----------

def main():
    parser = argparse.ArgumentParser(
        description="PDF OCR 工具（auto / ocrmypdf / paddle_api / mineru_api）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 默认推荐：自动后端
  # 已配置 PaddleOCR 时优先 Paddle，其次 MinerU，最后回退本地 ocrmypdf
  python3 scripts/pdf-ocr.py -i input.pdf -o output.pdf

  # 敏感材料强制不外传
  python3 scripts/pdf-ocr.py -i input.pdf -o output.pdf --local-only

  # 强制使用 ocrmypdf
  python3 scripts/pdf-ocr.py -i input.pdf -o output.pdf --backend local_ocrmypdf

  # 预留接口：接入外部 PaddleOCR API
  python3 scripts/pdf-ocr.py -i input.pdf -o output.pdf \\
    --backend paddle_api --paddle-api-endpoint http://127.0.0.1:18000/ocr

  # 预留接口：接入 MinerU API
  python3 scripts/pdf-ocr.py -i input.pdf -o output.pdf \\
    --backend mineru_api --mineru-api-base https://mineru.net
        """,
    )

    parser.add_argument("--input", "-i", required=True, help="输入 PDF 文件")
    parser.add_argument("--output", "-o", required=False, help="输出 PDF 文件（默认保存到原文件同目录，添加 _OCR 后缀）")
    parser.add_argument(
        "--backend",
        choices=["auto", "local_ocrmypdf", "paddle_api", "mineru_api"],
        default="auto",
        help=(
            "OCR 后端：auto（已配置时 Paddle/MinerU 优先，失败回退本地） / "
            "local_ocrmypdf / paddle_api / mineru_api"
        ),
    )
    parser.add_argument(
        "--mode",
        choices=["skip", "redo", "force"],
        default="skip",
        help="OCR 模式：skip(跳过已有文字) / redo(重做OCR层) / force(强制全页OCR)，默认 skip",
    )
    parser.add_argument(
        "--language",
        default="chi_sim+eng",
        help="语言参数（Tesseract 风格），默认 chi_sim+eng。",
    )
    parser.add_argument(
        "--output-type",
        choices=["pdf", "pdfa"],
        default="pdf",
        help="输出类型，默认 pdf（保真优先）",
    )
    parser.add_argument(
        "--optimize",
        type=int,
        choices=[0, 1, 2, 3],
        default=0,
        help="优化级别 0-3，默认 0（保真优先）",
    )
    parser.add_argument(
        "--skip-big",
        type=float,
        default=50.0,
        help="跳过大图页阈值（MP），默认 50",
    )
    parser.add_argument(
        "--tesseract-timeout",
        type=int,
        default=180,
        help="Tesseract 单页超时（秒），默认 180",
    )
    parser.add_argument("--jobs", type=int, help="并行任务数（可选）")
    parser.add_argument("--sidecar", help="导出 OCR 文本 sidecar 文件路径（可选）")
    parser.add_argument(
        "--fast-web-view",
        type=float,
        help="线性化参数（MB），例如 1.0；不填则使用 ocrmypdf 默认值",
    )

    parser.add_argument(
        "--preprocessed",
        action="store_true",
        help="输入文件已经完成预处理（将跳过 rotate/deskew/clean）",
    )
    parser.add_argument(
        "--no-rotate-pages",
        action="store_true",
        help="禁用自动旋转检测（仅在未使用 --preprocessed 时生效）",
    )
    parser.add_argument(
        "--no-deskew",
        action="store_true",
        help="禁用自动倾斜矫正（仅在未使用 --preprocessed 时生效）",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="禁用去噪 clean（仅在未使用 --preprocessed 时生效）",
    )

    # 历史保留：本地 Paddle 双层参数（隐藏，不再作为公开选项）
    parser.add_argument("--paddle-lang", default="", help=argparse.SUPPRESS)
    parser.add_argument(
        "--paddle-profile",
        choices=["auto", "quality", "balanced", "speed"],
        default="auto",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--paddle-long-doc-pages",
        type=int,
        default=60,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--paddle-dpi",
        type=int,
        default=300,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--paddle-det-limit-side-len",
        type=int,
        default=1536,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--paddle-det-model-name",
        default="",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--paddle-rec-model-name",
        default="",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--paddle-min-score",
        type=float,
        default=0.5,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--paddle-skip-text-min-chars",
        type=int,
        default=1,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--paddle-textline-orientation",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--paddle-use-gpu", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--no-paddle-cjk-space-normalize",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--keep-paddle-model-source-check",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--paddle-model-source",
        choices=["huggingface", "bos"],
        help=argparse.SUPPRESS,
    )

    parser.add_argument("--dry-run", action="store_true", help="仅输出命令，不实际执行")
    parser.add_argument("--quiet", "-q", action="store_true", help="安静模式")
    parser.add_argument(
        "--env-file",
        default=DEFAULT_ENV_FILE_PATH,
        help=f".env 文件路径（默认 {DEFAULT_ENV_FILE_PATH}）",
    )
    parser.add_argument(
        "--no-env-file",
        action="store_true",
        help="禁用 .env 自动加载",
    )
    parser.add_argument(
        "--api-order",
        help=(
            "auto 模式下外部 API 顺序，逗号分隔（例如 paddle,mineru）；"
            f"不传则读取 {DEFAULT_OCR_API_ORDER_ENV} 或按 .env 配置顺序推断"
        ),
    )
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="强制不调用外部 OCR API，仅使用本地 ocrmypdf",
    )
    parser.add_argument(
        "--allow-external-upload",
        action="store_true",
        help="兼容旧版本；auto 现已默认使用已配置 API，如需禁止外传请用 --local-only",
    )
    parser.add_argument(
        "--archive-results",
        action="store_true",
        help="显式归档 OCR 可读文本和元数据；默认不归档案件材料",
    )

    # PaddleOCR API 预留参数
    parser.add_argument(
        "--paddle-model",
        choices=SUPPORTED_PADDLE_MODELS,
        default="PP-OCRv6",
        help=(
            "PaddleOCR API 模型（默认 PP-OCRv6，使用行级坐标匹配文字层；"
            "另支持 PaddleOCR-VL-1.5/1.6 与 PP-StructureV3）"
        ),
    )
    parser.add_argument(
        "--paddle-api-endpoint",
        help="外部 PaddleOCR API 地址（POST JSON，官方常见为 /ocr 或 /layout-parsing）",
    )
    parser.add_argument(
        "--paddle-api-endpoint-env",
        default=DEFAULT_PADDLE_API_ENDPOINT_ENV,
        help=f"外部 API endpoint 环境变量名（默认 {DEFAULT_PADDLE_API_ENDPOINT_ENV}）",
    )
    parser.add_argument(
        "--paddle-api-key-env",
        default=DEFAULT_PADDLE_API_KEY_ENV,
        help=f"API Key 环境变量名（默认 {DEFAULT_PADDLE_API_KEY_ENV}）",
    )
    parser.add_argument(
        "--paddle-api-timeout",
        type=int,
        default=180,
        help="Paddle API 请求超时（秒），默认 180",
    )
    parser.add_argument(
        "--paddle-api-retries",
        type=int,
        default=1,
        help="Paddle API 重试次数，默认 1",
    )
    parser.add_argument(
        "--paddle-api-extra-json",
        help="额外 JSON 配置文件路径（会合并进 API payload）",
    )
    parser.add_argument(
        "--paddle-api-protocol",
        choices=["auto", "official", "legacy"],
        default="auto",
        help="API 协议：auto(官方优先并兼容旧协议)/official/legacy，默认 auto",
    )
    parser.add_argument(
        "--no-paddle-fallback-local",
        action="store_true",
        help="Paddle API 失败时不回退到本地 ocrmypdf（默认会回退）",
    )
    parser.add_argument(
        "--no-photo-correct",
        action="store_true",
        help="禁用拍照件自动矫正（默认启用：检测到方向偏差时自动下载 API 预处理图替换）",
    )

    # PaddleOCR-VL / PP-Structure 服务端预处理参数；VL-1.5 另支持版面形状参数
    parser.add_argument(
        "--paddle-vl-layout-detection",
        action="store_true",
        default=True,
        help="VL: 启用版面区域检测+排序（默认开启）",
    )
    parser.add_argument(
        "--paddle-vl-no-layout-detection",
        action="store_true",
        help="VL: 禁用版面区域检测",
    )
    parser.add_argument(
        "--paddle-vl-chart-recognition",
        action="store_true",
        help="VL: 启用图表解析（柱状图/饼图转表格）",
    )
    parser.add_argument(
        "--paddle-vl-doc-orientation",
        action="store_true",
        help="VL: 启用图片方向矫正（0°/90°/180°/270°）",
    )
    parser.add_argument(
        "--paddle-vl-doc-unwarping",
        action="store_true",
        help="VL: 启用图片扭曲矫正（褶皱/倾斜）",
    )
    parser.add_argument(
        "--paddle-vl-layout-shape-mode",
        choices=["rect", "quad", "poly", "auto"],
        default="rect",
        help="VL: 检测框几何形状（默认 rect）",
    )

    # OCR dump/resume 参数
    parser.add_argument(
        "--ocr-dump",
        metavar="FILE",
        help="OCR dump 模式：完成 OCR 后将结果保存到 JSON 文件，不生成 PDF（供 agent 审查）",
    )
    parser.add_argument(
        "--dump-and-pdf",
        action="store_true",
        help="配合 --ocr-dump 使用：保存 dump 后继续生成双层 PDF（默认 --ocr-dump 仅 dump 不出 PDF）",
    )
    parser.add_argument(
        "--ocr-resume",
        metavar="FILE",
        help="OCR resume 模式：从 dump 文件加载 OCR 结果，跳过 API 调用（配合 --ocr-dump 使用）",
    )
    parser.add_argument(
        "--corrections-file",
        metavar="FILE",
        help="Agent 修正文件：JSON 格式 [{from, to}, ...]，在规则纠错后应用",
    )

    # ActualText / 自然段参数（默认开启，让从 PDF 复制的文字按段落连续）
    parser.add_argument(
        "--actualtext",
        dest="actualtext",
        action="store_true",
        default=True,
        help="（默认开启）把自然段以 /ActualText 写入 PDF 文字层，让复制/搜索得到段落级连续文本",
    )
    parser.add_argument(
        "--no-actualtext",
        dest="actualtext",
        action="store_false",
        help="关闭 ActualText 写入；PDF 复制仍按物理行断行，需用独立 Markdown 取段落文本",
    )
    parser.add_argument(
        "--layout-dump",
        metavar="FILE",
        help="已有 PP-StructureV3/VL 版面 dump JSON；ActualText 融合时复用，避免再调一次 API",
    )
    parser.add_argument(
        "--clean-text-output",
        metavar="FILE",
        help="显式输出按自然段整理的本地 Markdown；默认不生成案件正文副本",
    )

    # MinerU API 参数
    parser.add_argument(
        "--mineru-api-base",
        help="MinerU API Base 地址（例如 https://mineru.net）",
    )
    parser.add_argument(
        "--mineru-api-base-env",
        default=DEFAULT_MINERU_API_BASE_ENV,
        help=f"MinerU API Base 环境变量名（默认 {DEFAULT_MINERU_API_BASE_ENV}）",
    )
    parser.add_argument(
        "--mineru-api-token-env",
        default=DEFAULT_MINERU_API_TOKEN_ENV,
        help=f"MinerU Token 环境变量名（默认 {DEFAULT_MINERU_API_TOKEN_ENV}）",
    )
    parser.add_argument(
        "--mineru-user-token-env",
        default=DEFAULT_MINERU_USER_TOKEN_ENV,
        help=f"MinerU 用户 Token 环境变量名（默认 {DEFAULT_MINERU_USER_TOKEN_ENV}）",
    )
    parser.add_argument(
        "--mineru-api-timeout",
        type=int,
        default=180,
        help="MinerU API 请求超时（秒），默认 180",
    )
    parser.add_argument(
        "--mineru-poll-interval",
        type=int,
        default=2,
        help="MinerU 任务轮询间隔（秒），默认 2",
    )
    parser.add_argument(
        "--mineru-poll-timeout",
        type=int,
        default=1800,
        help="MinerU 任务轮询超时（秒），默认 1800",
    )
    parser.add_argument(
        "--mineru-model-version",
        default="",
        help="MinerU 模型版本（可选，如 vlm）",
    )
    parser.add_argument(
        "--mineru-language",
        default="",
        help="MinerU 语言参数（可选，如 auto/ch/en）",
    )
    parser.add_argument(
        "--mineru-enable-formula",
        action="store_true",
        help="MinerU 启用公式识别（默认关闭）",
    )
    parser.add_argument(
        "--mineru-enable-table",
        action="store_true",
        help="MinerU 启用表格识别（默认关闭）",
    )
    parser.add_argument(
        "--mineru-api-extra-json",
        help="额外 MinerU create payload JSON 文件路径",
    )

    args = parser.parse_args()
    args.backend_used = args.backend
    args.paddle_dpi_user_set = _cli_arg_present("--paddle-dpi")
    args.paddle_det_limit_user_set = _cli_arg_present("--paddle-det-limit-side-len")

    # --paddle-vl-no-layout-detection 覆盖默认值
    if args.paddle_vl_no_layout_detection:
        args.paddle_vl_layout_detection = False

    # 将 argparse namespace 转为 kwargs 传给 run_ocr
    kwargs = vars(args)

    try:
        run_ocr(**kwargs)
    except Exception as e:
        print(f"\n错误: OCR 后端执行失败 - {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
