#!/usr/bin/env python3
"""
PDF Processor 运行时辅助工具。

统一处理：
1. `.env` 加载与别名兼容
2. 缺失依赖提示
3. 首次安装较慢的提醒
4. HTTP 工具函数
5. API 环境变量常量
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib import request


# ---------- 环境变量常量 ----------

DEFAULT_PADDLE_API_ENDPOINT_ENV = "PADDLE_OCR_API_ENDPOINT"
DEFAULT_PADDLE_API_KEY_ENV = "PADDLE_OCR_API_KEY"
DEFAULT_MINERU_API_BASE_ENV = "MINERU_API_BASE"
DEFAULT_MINERU_API_TOKEN_ENV = "MINERU_API_TOKEN"
DEFAULT_MINERU_USER_TOKEN_ENV = "MINERU_USER_TOKEN"


# ---------- 依赖检测 ----------

HEAVY_INSTALL_KEYS = {
    "ocrmypdf",
    "paddleocr",
    "paddlepaddle",
    "opencv-python",
    "pdf2image",
    "pymupdf",
    "poppler",
    "tesseract",
    "tesseract-chi_sim",
}


def strip_quoted(value: str) -> str:
    """去掉简单的首尾引号。"""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_env_file(env_file: str, quiet: bool = False) -> bool:
    """加载 .env 文件（不覆盖现有环境变量）。"""
    path = Path(env_file).expanduser()
    if not path.exists():
        return False

    loaded_any = False
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        if raw.startswith("export "):
            raw = raw[len("export "):].strip()
        if "=" not in raw:
            continue

        key, value = raw.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue

        os.environ[key] = strip_quoted(value)
        loaded_any = True

    if loaded_any and not quiet:
        print(f"已加载环境配置: {path}")
    return loaded_any


def apply_api_env_aliases() -> None:
    """兼容常见 API 环境变量别名。"""
    if not os.getenv("PADDLE_OCR_API_ENDPOINT", "").strip():
        api_url = os.getenv("API_URL", "").strip()
        if api_url:
            os.environ["PADDLE_OCR_API_ENDPOINT"] = api_url

    if not os.getenv("PADDLE_OCR_API_KEY", "").strip():
        token = os.getenv("TOKEN", "").strip()
        if token:
            os.environ["PADDLE_OCR_API_KEY"] = token

    if not os.getenv("MINERU_API_BASE", "").strip():
        alias_base = (
            os.getenv("MINERU_API_BASE_URL", "").strip()
            or os.getenv("MINERU_BASE_URL", "").strip()
            or os.getenv("MINERU_API_ENDPOINT", "").strip()
        )
        if alias_base:
            os.environ["MINERU_API_BASE"] = alias_base

    if not os.getenv("MINERU_API_TOKEN", "").strip():
        alias_token = (
            os.getenv("MINERU_TOKEN", "").strip()
            or os.getenv("MINERU_API_KEY", "").strip()
        )
        if alias_token:
            os.environ["MINERU_API_TOKEN"] = alias_token


def _dedupe(items: list[str] | tuple[str, ...] | None) -> list[str]:
    seen = set()
    result = []
    for item in items or []:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _should_warn_slow_install(missing_python: list[str], missing_system: list[str]) -> bool:
    combined = {item.lower() for item in missing_python + missing_system}
    return len(combined) >= 2 or bool(combined & HEAVY_INSTALL_KEYS)


def print_dependency_help(
    title: str,
    *,
    missing_python: list[str] | None = None,
    missing_system: list[str] | None = None,
    install_commands: list[str] | None = None,
    extra_notes: list[str] | None = None,
    stream=None,
) -> None:
    """打印统一的依赖缺失提示。"""
    stream = stream or sys.stderr
    missing_python = _dedupe(missing_python)
    missing_system = _dedupe(missing_system)
    install_commands = _dedupe(install_commands)
    extra_notes = _dedupe(extra_notes)

    print(f"错误: {title}缺少依赖。", file=stream)
    if missing_python:
        print("Python 包:", ", ".join(missing_python), file=stream)
    if missing_system:
        print("系统依赖:", ", ".join(missing_system), file=stream)

    if install_commands:
        print("\n建议安装命令:", file=stream)
        for command in install_commands:
            print(f"  {command}", file=stream)

    if _should_warn_slow_install(missing_python, missing_system):
        print(
            "\n提示: 如果这是第一次安装，这一步可能会比较慢，通常需要几分钟，"
            "Paddle / OCR / 图像处理依赖在部分机器上可能需要更久。",
            file=stream,
        )
        if any(dep in {"paddleocr", "paddlepaddle"} for dep in missing_python):
            print("  - Paddle 首次安装后，首次运行还可能继续下载模型。", file=stream)
        if "ocrmypdf" in missing_python or "tesseract" in missing_system:
            print("  - ocrmypdf / Tesseract / 语言包的安装通常比纯 Python 包更慢。", file=stream)
        if any(dep in {"opencv-python", "pdf2image", "pymupdf", "poppler"} for dep in missing_python + missing_system):
            print("  - 图像处理相关依赖较多时，安装和首次验证也可能需要几分钟。", file=stream)

    if extra_notes:
        print("\n补充说明:", file=stream)
        for note in extra_notes:
            print(f"  - {note}", file=stream)


def exit_for_missing_dependencies(
    title: str,
    *,
    missing_python: list[str] | None = None,
    missing_system: list[str] | None = None,
    install_commands: list[str] | None = None,
    extra_notes: list[str] | None = None,
) -> "NoReturn":
    """打印统一依赖提示并退出。"""
    print_dependency_help(
        title,
        missing_python=missing_python,
        missing_system=missing_system,
        install_commands=install_commands,
        extra_notes=extra_notes,
    )
    raise SystemExit(1)


# ---------- HTTP 工具函数 ----------

def http_post_json(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    """POST JSON 并返回 JSON。"""
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(url, data=raw, headers=headers, method="POST")
    with request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        return json.loads(body)


def http_get_json(url: str, headers: dict, timeout: int) -> dict:
    """GET JSON 并返回 JSON 对象。"""
    req = request.Request(url, headers=headers, method="GET")
    with request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        return json.loads(body)


def http_get_bytes(url: str, timeout: int) -> bytes:
    """GET 下载二进制数据。"""
    req = request.Request(url, method="GET")
    with request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def http_put_bytes(url: str, payload: bytes, headers: dict, timeout: int):
    """PUT 二进制数据。"""
    req = request.Request(url, data=payload, headers=headers, method="PUT")
    try:
        with request.urlopen(req, timeout=timeout) as _:
            return
    except Exception:
        # 对部分 OSS 预签名 URL，urllib 在某些网络栈下可能出现 Broken pipe，
        # 回退到 curl 提升兼容性。
        if shutil.which("curl") is None:
            raise

        with tempfile.NamedTemporaryFile(suffix=".bin", delete=True) as tf:
            tf.write(payload)
            tf.flush()

            cmd = ["curl", "-sS", "-X", "PUT", "-T", tf.name, "--max-time", str(timeout)]
            for k, v in (headers or {}).items():
                if k is None:
                    continue
                key = str(k).strip()
                if not key:
                    continue
                val = "" if v is None else str(v)
                cmd += ["-H", f"{key}: {val}"]
            cmd += [url]

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                detail = result.stderr.strip() or result.stdout.strip()
                raise RuntimeError(f"curl PUT 失败（退出码 {result.returncode}）: {detail}")


def http_post_multipart(
    url: str,
    fields: dict[str, str],
    files: dict[str, tuple[str, bytes]],
    headers: dict,
    timeout: int,
) -> dict:
    """POST multipart/form-data 并返回 JSON。files: {field_name: (filename, file_bytes)}。"""
    import uuid

    boundary = uuid.uuid4().hex
    parts = []

    for key, value in fields.items():
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode())
        parts.append(f"{value}\r\n".encode())

    for field_name, (filename, data) in files.items():
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'.encode()
        )
        parts.append(b"Content-Type: application/octet-stream\r\n\r\n")
        parts.append(data)
        parts.append(b"\r\n")

    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)

    req_headers = dict(headers) if headers else {}
    req_headers.pop("Content-Type", None)
    req = request.Request(url, data=body, headers=req_headers, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")

    with request.urlopen(req, timeout=timeout) as resp:
        resp_body = resp.read().decode("utf-8", errors="replace")
        return json.loads(resp_body)


def http_get_text(url: str, timeout: int) -> str:
    """GET 下载文本内容。"""
    req = request.Request(url, method="GET")
    with request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def response_success(resp: dict) -> bool:
    """判断 API 响应是否成功。"""
    if "errorCode" in resp:
        return str(resp.get("errorCode")) in {"0", "200"}
    if "success" in resp:
        return bool(resp["success"])
    code = resp.get("code")
    if code is None:
        return True
    return str(code) in {"0", "100", "200"}
