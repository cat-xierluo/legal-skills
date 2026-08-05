#!/usr/bin/env python3
"""对 Skill 做确定性静态安全扫描（对应 SkillSpector 的漏洞模式）。

本扫描器把 security-assessment-standards.md 中原本依赖 LLM 人工判断的检查项
转成可复算的静态门禁，覆盖以下 SkillSpector 对应模式：

- Dangerous Code Execution      -> subprocess / os.system / eval / exec / 动态导入
- Data Exfiltration             -> urllib / requests / httpx / socket / websocket 等网络外传
- Credential Access             -> os.environ 读取 / .env / SSH / AWS / 凭证文件访问
- Supply Chain                  -> 未固定版本依赖、脚本内运行时安装（pip/npm/playwright）
- Unpinned Dependencies         -> requirements.txt / package.json 未 pin 版本
- Taint Tracking                -> env/argv/input/network/file 来源值流入 subprocess 命令/参数
- File System Enumeration       -> os.walk/listdir/glob 扫描用户主目录或敏感目录
- Missing User Warnings         -> 存在高风险能力但文档未披露（网络、自动安装、凭据等）
- MCP Least Privilege           -> 脚本用到执行/网络/环境变量/文件能力但 SKILL.md 无权限声明；
                                    MCP 配置出现通配符权限（*）
- Description-Behavior Mismatch -> 文档引导执行未披露的高风险动作（发布/仓库变更/提权/外传），
                                    即 scope creep
- Unicode Deception             -> 零宽字符 / RTL 覆盖等隐藏字符
- Context-Inappropriate Capability -> 轻量描述 + 未披露的重型能力（外链下载/自动安装）
- Prompt Injection              -> SKILL.md/references 含忽略上层指令、绕过限制等表述
- Hardcoded Secrets             -> 真实 API Key / Token / 私钥

用法：
  python3 scripts/security_scan.py audit --candidate-root /path/to/skill [--output out.json] [--online]
  python3 scripts/security_scan.py batch --root /path/to/skills [--output out.json] [--online]

退出码：
  0  PASS（无 critical/high，允许 medium/low）
  1  FAIL（存在 critical 或 high finding）
  2  范围错误（未发现 SKILL.md，或参数不合法）

--online 会请求 OSV API（https://api.osv.dev）查询已知漏洞，默认离线只做版本 pin 检查。
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

SCHEMA_VERSION = 1

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "archive",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "vendor",
    "dist",
    "build",
    ".venv",
    "venv",
    ".tox",
    ".nox",
    ".eggs",
}

# ---------------------------------------------------------------------------
# 能力信号定义：capability -> 披露关键词（用于 Missing User Warnings 判定）
# ---------------------------------------------------------------------------

@dataclass
class CapabilitySignal:
    capability: str          # network / subprocess / install / credential / filesystem / browser / delete / dynamic_import
    category: str            # 对应 SkillSpector 分类
    severity: str            # critical / high / medium / low / info
    file: str
    line: int
    code: str
    message: str
    is_test: bool = False
    confidence: float = 0.9

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": f"SEC-{self.capability.upper()}",
            "capability": self.capability,
            "severity": self.severity,
            "category": self.category,
            "file": self.file,
            "line": self.line,
            "code": self.code[:220],
            "message": self.message,
            "confidence": self.confidence,
            "is_test": self.is_test,
        }


# 各能力对应的文档披露关键词（命中任一即认为已披露）
DISCLOSURE_KEYWORDS = {
    "network": ["网络", "外链", "外部 URL", "HTTP", "https://", "请求", "下载图片", "网络请求", "外网", "远端", "remote"],
    "subprocess": ["执行", "subprocess", "命令", "渲染", "调用", "shell", "外部工具", "浏览器自动化", "mmdc", "playwright", "rsvg"],
    "install": ["安装", "pip install", "npm install", "playwright install", "依赖", "requirements", "install"],
    "credential": ["环境变量", "凭证", "账号", "密码", "密钥", "token", "Token", ".env", "凭据", "用户名"],
    "filesystem": ["文件", "输出", "写入", "目录", "读取", "生成", "模板", "路径"],
    "browser": ["浏览器", "playwright", "无头", "headless", "Chromium"],
    "delete": ["删除", "清理", "移除"],
    "dynamic_import": ["动态导入", "importlib", "__import__"],
}

# SKILL.md 中"权限声明"章节的存在性关键词（MCP Least Privilege 判定）
PERMISSION_SECTION_KEYWORDS = [
    "所需权限", "权限声明", "安全说明", "能力声明", "能力边界", "权限边界",
    "权限与安全", "安全提示", "安全风险", "权限", "允许但需说明",
]

# 轻量描述信号：描述/正文暗示"简单转换/格式化"，却带未披露重型能力 -> Context-Inappropriate
LIGHTWEIGHT_SIGNALS = ["转换", "格式化", "简单", "轻量", "查看", "整理", "排版", "convert", "format", "simple", "view"]


# ---------------------------------------------------------------------------
# 文件收集
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SourceFile:
    path: Path
    relative: str
    text: str
    lines: tuple[str, ...]
    is_test: bool
    is_public_doc: bool  # SKILL.md / README / references 等面向用户的文档


def _is_skipped(relative: Path) -> bool:
    return any(part in SKIP_DIRS for part in relative.parts)


def _is_test_path(relative: Path) -> bool:
    lowered_parts = {part.lower() for part in relative.parts}
    name = relative.name.lower()
    return bool(
        lowered_parts & {"test", "tests", "eval", "evals", "fixtures"}
        or name.startswith("test_")
        or name.startswith("test-")
        or name.startswith("smoke-")
        or name.startswith("run-evals")
        or name.endswith("_test.py")
        or name.endswith("_tests.py")
        or "regression" in name
    )


def _is_public_doc(relative: Path) -> bool:
    name = relative.name.lower()
    if name == "skill.md" or name == "readme.md":
        return True
    parts = [p.lower() for p in relative.parts]
    return bool(parts and parts[0] == "references") and name.endswith(".md")


PY_SUFFIXES = {".py"}
SH_SUFFIXES = {".sh", ".bash"}
DOC_SUFFIXES = {".md"}
DEP_FILE_NAMES = {"requirements.txt", "package.json", "pyproject.toml", "Pipfile", "Gemfile"}
MCP_FILE_NAMES = {"mcp.json", ".mcp.json", "mcp-servers.json", "mcp-config.json"}
TEXT_SUFFIXES = PY_SUFFIXES | SH_SUFFIXES | DOC_SUFFIXES | DEP_FILE_NAMES


def _iter_regular_files(candidate_root: Path) -> Iterable[Path]:
    """递归列出普通文件，不跟随符号链接（避免把外部私有仓库目录扫进来）。"""
    for dirpath, dirnames, filenames in os.walk(candidate_root, followlinks=False):
        dirpath_path = Path(dirpath)
        # 跳过符号链接目录与 SKIP_DIRS（就地裁剪，避免下钻）
        dirnames[:] = [
            d for d in dirnames
            if d not in SKIP_DIRS and not (dirpath_path / d).is_symlink()
        ]
        for name in filenames:
            path = dirpath_path / name
            if path.is_symlink():
                continue
            yield path


def _read_sources(candidate_root: Path) -> list[SourceFile]:
    sources: list[SourceFile] = []
    for path in sorted(_iter_regular_files(candidate_root)):
        if not path.is_file():
            continue
        relative = path.relative_to(candidate_root)
        if _is_skipped(relative):
            continue
        if path.name in DEP_FILE_NAMES or path.name in MCP_FILE_NAMES or path.suffix.lower() in TEXT_SUFFIXES:
            text = path.read_text(encoding="utf-8", errors="replace")
            sources.append(
                SourceFile(
                    path=path,
                    relative=relative.as_posix(),
                    text=text,
                    lines=tuple(text.splitlines()),
                    is_test=_is_test_path(relative),
                    is_public_doc=_is_public_doc(relative),
                )
            )
    return sources


def _discover_skill_roots(collection_root: Path) -> list[Path]:
    roots: list[Path] = []
    for path in sorted(_iter_regular_files(collection_root)):
        if path.name == "SKILL.md" and path.is_file():
            roots.append(path.parent)
    return roots


# ---------------------------------------------------------------------------
# Python AST 扫描
# ---------------------------------------------------------------------------

# 网络外传调用
NETWORK_CALLS = {
    "urlopen": "urllib.request",
    "urlretrieve": "urllib.request",
    "urlopen": "urllib",
    "get": "requests/httpx/aiohttp",
    "post": "requests/httpx/aiohttp",
    "put": "requests/httpx/aiohttp",
    "patch": "requests/httpx/aiohttp",
    "delete": "requests/httpx/aiohttp",
    "request": "requests",
    "send": "websocket/socket",
    "create_connection": "socket",
    "connect": "socket/websocket",
    "download": "wget/requests",
}

# subprocess / 执行类
SUBPROCESS_NAMES = {"run", "call", "Popen", "check_output", "check_call", "getoutput", "getstatusoutput"}
OS_SYSTEM = {"system", "popen", "spawnl", "spawnv", "execv", "execl"}

# 敏感文件/路径信号
SENSITIVE_PATH_PATTERNS = [
    r"\.env",
    r"\.ssh[\\/]",
    r"id_rsa",
    r"id_ed25519",
    r"\.aws[\\/]",
    r"credentials",
    r"\.gnupg",
    r"\.netrc",
    r"\.pgpass",
    r"secret",
    r"token",
    r"password",
    r"passwd",
    r"key[\\/]",
    r"keystore",
    r"\.pem",
    r"\.p12",
    r"\.pfx",
]

# 硬编码凭证（跳过 .example / 占位符文件）
SECRET_RE = re.compile(
    r"("
    r"sk-[A-Za-z0-9]{16,}|"                      # OpenAI
    r"AKIA[0-9A-Z]{16}|"                          # AWS Access Key
    r"ghp_[A-Za-z0-9]{30,}|"                      # GitHub PAT
    r"xox[baprs]-[A-Za-z0-9-]{20,}|"              # Slack token
    r"-----BEGIN (RSA|OPENSSH|EC|PGP|DSA) PRIVATE KEY|"
    r"(?:(?:api[_-]?key|apikey|secret|token|password|passwd|pwd)\s*[=:]\s*)[\"']([^\"'\s]{8,})[\"']"
    r")",
    re.IGNORECASE,
)

INSTALL_RE = re.compile(r"(?:pip|pip3)\s+install|npm\s+(?:i|install)|playwright\s+install|yarn\s+add", re.IGNORECASE)
DOWNLOAD_EXEC_RE = re.compile(r"curl[^|\n]*\|\s*(?:sudo\s+)?(?:sh|bash)|wget[^|\n]*\|\s*(?:sudo\s+)?(?:sh|bash)", re.IGNORECASE)
PRIVILEGE_RE = re.compile(r"\bsudo\b|chmod\s+777|setuid", re.IGNORECASE)
PERSISTENCE_RE = re.compile(r"crontab|launchctl\s+load|systemctl\s+enable|LaunchAgents|schtasks", re.IGNORECASE)

# 提示注入：只识别"指令式"表述；安全文档里"检查是否含 X / 提示注入 / 报告话术"、CLI 参数说明、
# 禁止性表述（"不允许静默执行"）、用户指引（"不要静默忽略更新提示"）等描述性上下文不算。
PROMPT_INJECTION_PATTERNS = [
    # 直接指令忽略/无视指令类：对象必须带权威来源（系统/开发者/用户/上层/之前/所有等），
    # 避免命中"忽略更新提示/忽略路径"等良性表述。
    r"(?:请|务必|必须|应当|现在|立即|从现在开始|在此之后)?[^。\n]{0,6}(?:忽略|无视|不再遵守)"
    r"[^\s。\n]{0,12}(?:系统|开发者|用户|上层|平台|上级|安全|所有|全部|任何|你|之前|以上|这些)"
    r"[^\s。\n]{0,6}(?:指令|提示|规则|要求|内容|消息)",
    # 隐藏/静默执行
    r"(?:隐藏|静默|悄悄)(?:执行|进行|运行|操作|处理)",
    # 绕过/跳过限制：须伴随动作动词（"跳过所有权限 | 沙箱专用"这类 CLI 说明不命中）
    r"(?:绕过|跳过|避开)(?:所有|任何)?(?:安全|权限|验证|检查|限制)[^。\n]{0,8}(?:执行|运行|继续|操作|然后)",
    # 不要遵守/无需遵守
    r"(?:不要|无需|不用)(?:遵守|理会|遵循)(?:系统|开发者|用户|上层|任何)?\S{0,6}(?:指令|规则|提示|要求)",
]
PROMPT_INJECTION_NEGATIVE = [
    "提示注入", "提示词", "注入", "是否", "检查", "审查", "检测", "判定", "评估",
    "表述", "话术", "要求", "警告", "严重", "欺骗性", "风险", "威胁", "说明",
    "描述", "分类", "类别", "维度", "样本", "用例",
    "gitignore", "被忽略", "忽略的文件", "忽略路径", "本地忽略",
    "不允许", "禁止", "不得", "严禁", "避免",
    "参数", "flag", "命令行", "CLI", "沙箱",
]


def _is_prompt_injection_line(line: str) -> bool:
    if any(n in line for n in PROMPT_INJECTION_NEGATIVE):
        return False
    return any(re.search(p, line, re.IGNORECASE) for p in PROMPT_INJECTION_PATTERNS)


def _resolve_call_base(func: ast.AST) -> tuple[str, str]:
    """解析调用链，返回 (根名字, 属性链)。os.environ.get -> ('os', 'environ.get')。"""
    chain: list[str] = []
    node = func
    while isinstance(node, ast.Attribute):
        chain.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        return node.id, ".".join(reversed(chain))
    return "", ".".join(reversed(chain))


def _collect_capabilities_ast(source: SourceFile) -> list[CapabilitySignal]:
    findings: list[CapabilitySignal] = []
    try:
        tree = ast.parse(source.text)
    except SyntaxError:
        findings.append(
            CapabilitySignal(
                capability="syntax_error", category="Dangerous Code Execution",
                severity="info", file=source.relative, line=1, code="",
                message=f"无法解析 Python 语法（{source.relative}），跳过 AST 扫描。",
                is_test=source.is_test, confidence=0.9,
            )
        )
        return findings

    def _line(node: ast.AST) -> int:
        return getattr(node, "lineno", 1)

    def _code_lines(node: ast.AST) -> str:
        lineno = _line(node)
        return source.lines[lineno - 1].strip() if 0 < lineno <= len(source.lines) else ""

    for node in ast.walk(tree):
        # subprocess.run / call / Popen ...
        if isinstance(node, ast.Call):
            func = node.func
            fname = getattr(func, "attr", None) or getattr(func, "id", None)
            base, chain = _resolve_call_base(func)

            # subprocess 执行
            if fname in SUBPROCESS_NAMES and base == "subprocess":
                shell = False
                for kw in node.keywords:
                    if kw.arg == "shell" and isinstance(kw.value, ast.Constant):
                        shell = bool(kw.value.value)
                sev = "high" if shell else "medium"
                findings.append(
                    CapabilitySignal(
                        capability="subprocess", category="Dangerous Code Execution",
                        severity=sev, file=source.relative, line=_line(node),
                        code=_code_lines(node),
                        message=f"subprocess.{fname} 调用外部进程（shell={shell}）。"
                                + ("shell=True 有命令注入风险，应改用参数数组。" if shell else "命令应使用参数数组，避免拼接不可信输入。"),
                        is_test=source.is_test, confidence=0.93,
                    )
                )
            # os.system / os.popen
            elif fname in OS_SYSTEM and base == "os":
                sev = "high" if fname == "system" else "medium"
                findings.append(
                    CapabilitySignal(
                        capability="subprocess", category="Dangerous Code Execution",
                        severity=sev, file=source.relative, line=_line(node),
                        code=_code_lines(node),
                        message=f"os.{fname} 通过 shell 执行命令，若拼接不可信输入存在命令注入风险。",
                        is_test=source.is_test, confidence=0.95,
                    )
                )
            # 网络外传
            elif fname in NETWORK_CALLS and base in {
                "requests", "httpx", "aiohttp", "urllib", "socket", "websocket", "wget",
            }:
                findings.append(
                    CapabilitySignal(
                        capability="network", category="Data Exfiltration",
                        severity="medium", file=source.relative, line=_line(node),
                        code=_code_lines(node),
                        message=f"{base}.{chain} 发起外部网络请求（外传/下载）。",
                        is_test=source.is_test, confidence=0.9,
                    )
                )
            # eval / exec
            elif fname in {"eval", "exec"} and not isinstance(func, ast.Attribute):
                findings.append(
                    CapabilitySignal(
                        capability="dynamic_import", category="Dangerous Code Execution",
                        severity="high", file=source.relative, line=_line(node),
                        code=_code_lines(node),
                        message=f"{fname}() 动态执行代码，属高风险动态导入/混淆信号。",
                        is_test=source.is_test, confidence=0.9,
                    )
                )
            # 动态导入
            elif fname in {"__import__", "import_module"} or (
                fname == "import_module" and base == "importlib"
            ):
                findings.append(
                    CapabilitySignal(
                        capability="dynamic_import", category="Dangerous Code Execution",
                        severity="medium", file=source.relative, line=_line(node),
                        code=_code_lines(node),
                        message="动态导入（__import__ / importlib.import_module），需确认导入源可信。",
                        is_test=source.is_test, confidence=0.85,
                    )
                )
            # 安装类（subprocess 参数含 pip install）
            elif fname in SUBPROCESS_NAMES and base == "subprocess":
                args_text = ast.get_source_segment(source.text, node) or ""
                if INSTALL_RE.search(args_text):
                    findings.append(
                        CapabilitySignal(
                            capability="install", category="Supply Chain",
                            severity="high", file=source.relative, line=_line(node),
                            code=_code_lines(node),
                            message="脚本运行时通过 subprocess 自动安装依赖（pip/npm/playwright），"
                                    "未固定版本，存在供应链风险且无显式用户确认。",
                            is_test=source.is_test, confidence=0.93,
                        )
                    )
                if DOWNLOAD_EXEC_RE.search(args_text):
                    findings.append(
                        CapabilitySignal(
                            capability="install", category="Supply Chain",
                            severity="critical", file=source.relative, line=_line(node),
                            code=_code_lines(node),
                            message="检测到 '下载并执行远程代码'（curl|sh 或 wget|bash）模式，属 Hard Fail。",
                            is_test=source.is_test, confidence=0.97,
                        )
                    )
                if PRIVILEGE_RE.search(args_text):
                    findings.append(
                        CapabilitySignal(
                            capability="privilege", category="Privilege Escalation",
                            severity="high", file=source.relative, line=_line(node),
                            code=_code_lines(node),
                            message="subprocess 命令中含 sudo/chmod 777 等权限提升信号。",
                            is_test=source.is_test, confidence=0.85,
                        )
                    )

            # 环境变量读取（os.environ.get / os.getenv / os.environ['X']）
            elif base == "os" and (
                chain in {"get", "getenv", "environ.get"} or chain.startswith("environ.get")
            ):
                findings.append(
                    CapabilitySignal(
                        capability="credential", category="Credential Access",
                        severity="low", file=source.relative, line=_line(node),
                        code=_code_lines(node),
                        message="读取环境变量（os.environ.get / os.getenv），用于定位外部工具或读取账号凭证。",
                        is_test=source.is_test, confidence=0.9,
                    )
                )

        # os.environ 下标读取（os.environ['X'] / os.environ.get 已在上方 Call 分支处理）
        if isinstance(node, ast.Subscript):
            base, chain = _resolve_call_base(node.value)
            if base == "os" and chain == "environ":
                findings.append(
                    CapabilitySignal(
                        capability="credential", category="Credential Access",
                        severity="low", file=source.relative, line=_line(node),
                        code=_code_lines(node),
                        message="读取环境变量 os.environ[...]。",
                        is_test=source.is_test, confidence=0.9,
                    )
                )

        # open() / write_text 等敏感路径访问
        if isinstance(node, ast.Call):
            func = node.func
            fname = getattr(func, "attr", None) or getattr(func, "id", None)
            arg_texts: list[str] = []
            for arg in node.args:
                seg = ast.get_source_segment(source.text, arg)
                if seg:
                    arg_texts.append(seg)
            joined = " ".join(arg_texts)
            lowered = joined.lower()
            if fname == "open" or (fname == "write_text" and isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id in {"Path", "p"}):
                sensitive_hit = next(
                    (p for p in SENSITIVE_PATH_PATTERNS if re.search(p, lowered, re.IGNORECASE)),
                    None,
                )
                if sensitive_hit:
                    findings.append(
                        CapabilitySignal(
                            capability="filesystem", category="Sensitive File Access",
                            severity="high" if re.search(r"\.env|id_rsa|\.pem|\.aws|\.ssh", lowered) else "medium",
                            file=source.relative, line=_line(node),
                            code=_code_lines(node),
                            message=f"访问敏感路径（匹配 {sensitive_hit}）：{joined[:100]}",
                            is_test=source.is_test, confidence=0.9,
                        )
                    )
                write_mode = any(kw.arg == "mode" and isinstance(kw.value, ast.Constant) and kw.value.value in {"w", "a", "x", "wb", "ab"} for kw in node.keywords)
                if not write_mode:
                    for arg in node.args:
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value in {"w", "a", "x", "wb", "ab"}:
                            write_mode = True
                if write_mode:
                    findings.append(
                        CapabilitySignal(
                            capability="filesystem", category="File Write",
                            severity="info", file=source.relative, line=_line(node),
                            code=_code_lines(node),
                            message=f"写文件（open 模式 w/a/x）：{joined[:100]}",
                            is_test=source.is_test, confidence=0.9,
                        )
                    )

        # 删除操作（仅 os.shutil 系；XML Element.remove 等非文件删除不算）
        if isinstance(node, ast.Call):
            func = node.func
            fname = getattr(func, "attr", None)
            if fname in {"rmtree", "remove", "unlink"} and isinstance(func, ast.Attribute):
                base, chain = _resolve_call_base(func)
                if base not in {"os", "shutil"}:
                    continue
                if chain == "rmtree" or (chain in {"remove", "unlink"} and base == "shutil"):
                    sev, cap, msg = "medium", "delete", (
                        f"{base}.{chain}() 递归/批量删除，需确认删除边界（不应无确认删除用户数据）。"
                    )
                else:
                    sev, cap, msg = "info", "delete", (
                        f"{base}.{chain}() 删除单个文件（通常为临时文件清理）。"
                    )
                findings.append(
                    CapabilitySignal(
                        capability=cap, category="Destructive File Operation",
                        severity=sev, file=source.relative, line=_line(node),
                        code=_code_lines(node),
                        message=msg,
                        is_test=source.is_test, confidence=0.85,
                    )
                )

        # playwright（浏览器自动化）
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in {"playwright", "selenium"}:
                    findings.append(
                        CapabilitySignal(
                            capability="browser", category="Browser Automation",
                            severity="info", file=source.relative, line=_line(node),
                            code=_code_lines(node),
                            message="使用浏览器自动化库（playwright/selenium），会在本机启动浏览器。",
                            is_test=source.is_test, confidence=0.9,
                        )
                    )

    return findings


# ---------------------------------------------------------------------------
# Shell 脚本扫描
# ---------------------------------------------------------------------------

def _collect_capabilities_shell(source: SourceFile) -> list[CapabilitySignal]:
    findings: list[CapabilitySignal] = []

    def _add(capability: str, category: str, severity: str, line: int, pattern: str, message: str, confidence: float = 0.9):
        code = source.lines[line - 1].strip() if 0 < line <= len(source.lines) else ""
        findings.append(
            CapabilitySignal(
                capability=capability, category=category, severity=severity,
                file=source.relative, line=line, code=code, message=message,
                is_test=source.is_test, confidence=confidence,
            )
        )

    for lineno, line in enumerate(source.lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # echo/printf 只是打印提示文案，不是实际执行（如 echo "请先安装：npm install xxx"）
        if re.match(r"^(?:echo|printf)\b", stripped):
            continue
        # 运行时自动安装
        if re.search(r"pip(?:3)?\s+install|npm\s+(?:i|install)|yarn\s+add|playwright\s+install", line, re.IGNORECASE):
            _add(
                "install", "Supply Chain", "high", lineno, "install",
                "脚本运行时自动安装依赖（pip/npm/playwright install），未固定版本，"
                "会从网络拉取包/二进制，存在供应链风险且默认无用户确认。",
                0.93,
            )
        # 下载并执行
        if DOWNLOAD_EXEC_RE.search(line):
            _add(
                "install", "Supply Chain", "critical", lineno, "download_exec",
                "检测到 '下载并执行远程代码'（curl|sh 或 wget|bash），属 Hard Fail。",
                0.97,
            )
        # 权限提升
        if re.search(r"\bsudo\b|chmod\s+777|setuid", line):
            _add(
                "privilege", "Privilege Escalation", "high", lineno, "sudo",
                "脚本使用 sudo / chmod 777 等权限提升操作。",
                0.85,
            )
        # 持久化
        if re.search(r"crontab|launchctl\s+load|systemctl\s+enable|LaunchAgents|schtasks", line):
            _add(
                "persistence", "Persistence", "high", lineno, "persistence",
                "脚本配置定时任务/自启动（cron/launchd/systemd），需用户确认。",
                0.9,
            )
        # 环境变量读取
        if re.search(r"\$\{?(?:HOME|SSH_|AWS_|TOKEN|PASSWORD|SECRET|API_?KEY|GITHUB|PAT_)[A-Z0-9_]*\}?", line, re.IGNORECASE):
            _add(
                "credential", "Credential Access", "low", lineno, "env",
                "读取环境变量（含可能的凭证变量）。",
                0.85,
            )
        # 敏感文件
        if re.search(r"\.env|id_rsa|\.pem|\.aws|\.ssh|credentials", line, re.IGNORECASE):
            _add(
                "filesystem", "Sensitive File Access", "medium", lineno, "sensitive",
                "脚本访问敏感文件（.env/SSH/AWS/credentials）。",
                0.85,
            )
        # eval / 命令注入信号
        if re.search(r"\beval\b|`[^`]*\$\([^`]*\)", line):
            _add(
                "dynamic_import", "Dangerous Code Execution", "high", lineno, "eval",
                "shell 中使用 eval 或嵌套命令替换，存在注入风险。",
                0.8,
            )
    return findings


# ---------------------------------------------------------------------------
# 硬编码凭证扫描（全文件）
# ---------------------------------------------------------------------------

SECRET_SKIP_CONTEXT = [
    "mock", "fake", "dummy", "stub", "example", "sample", "placeholder", "demo",
    "fixture", "faker", "test_value", "dummy_value",
]
# 匹配到的"凭证值"含这些标记即视为占位符/变量引用，跳过
SECRET_SKIP_VALUE_MARKERS = [
    "$",                       # shell 变量引用 ${VAR} / $VAR
    "your", "here", "literal", "xxxx", "xxx", "你的", "请替换", "替换为", "填写",
    "your_", "token_here",
]


def _looks_like_placeholder(secret: str) -> bool:
    lowered = secret.lower()
    if any(k in lowered for k in SECRET_SKIP_CONTEXT):
        return True
    return any(m in lowered for m in SECRET_SKIP_VALUE_MARKERS)


def _scan_hardcoded_secrets(sources: list[SourceFile]) -> list[CapabilitySignal]:
    findings: list[CapabilitySignal] = []
    for source in sources:
        if ".example" in source.relative or source.relative.endswith(".example.yaml") or source.relative.endswith(".example.yml"):
            continue
        for lineno, line in enumerate(source.lines, 1):
            m = SECRET_RE.search(line)
            if not m:
                continue
            secret = m.group(0)
            if _looks_like_placeholder(secret):
                continue
            findings.append(
                CapabilitySignal(
                    capability="secret", category="Hardcoded Credential",
                    severity="critical", file=source.relative, line=lineno,
                    code=line.strip()[:220],
                    message="检测到疑似真实凭证（API Key/Token/私钥/密码），属 Hard Fail，必须删除并轮换。",
                    is_test=source.is_test, confidence=0.9,
                )
            )
    return findings


# ---------------------------------------------------------------------------
# 提示注入扫描（SKILL.md / references / README）
# ---------------------------------------------------------------------------

def _scan_prompt_injection(sources: list[SourceFile]) -> list[CapabilitySignal]:
    findings: list[CapabilitySignal] = []
    for source in sources:
        if not source.is_public_doc:
            continue
        for lineno, line in enumerate(source.lines, 1):
            if _is_prompt_injection_line(line):
                findings.append(
                    CapabilitySignal(
                        capability="prompt_injection", category="Prompt Injection",
                        severity="critical", file=source.relative, line=lineno,
                        code=line.strip()[:220],
                        message="文档含'忽略上层指令/绕过限制/隐藏执行'类表述。这些内容会进入系统提示，"
                                "属于提示词注入载体，必须删除而非改写。",
                        is_test=source.is_test, confidence=0.95,
                    )
                )
    return findings


# ---------------------------------------------------------------------------
# 依赖 pin / CVE 检查
# ---------------------------------------------------------------------------

def _scan_dependencies(source: SourceFile, online: bool) -> list[CapabilitySignal]:
    findings: list[CapabilitySignal] = []
    name = source.relative

    if name.endswith("requirements.txt"):
        for lineno, line in enumerate(source.lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("-"):
                continue
            # 去掉注释与行尾 extras
            pkg = re.split(r"\s+#", stripped)[0].strip()
            if not pkg:
                continue
            # 是否带版本约束
            has_pin = re.search(r"==|>=|<=|~=|!=|@\s", pkg)
            if not has_pin:
                pkg_name = pkg.split("[")[0].strip()
                findings.append(
                    CapabilitySignal(
                        capability="unpinned", category="Supply Chain",
                        severity="low", file=source.relative, line=lineno,
                        code=stripped[:220],
                        message=f"依赖未固定版本：{pkg_name}。建议 pin 到具体版本（如 {pkg_name}==x.y.z）。",
                        is_test=source.is_test, confidence=0.94,
                    )
                )
            elif online:
                _check_osv(findings, source, lineno, stripped, ecosystem="PyPI")

    elif name.endswith("package.json"):
        try:
            data = json.loads(source.text)
        except json.JSONDecodeError:
            return findings
        for section in ("dependencies", "devDependencies"):
            deps = data.get(section) or {}
            for pkg, ver in deps.items():
                ver_str = str(ver)
                if ver_str in {"*", "latest", ""} or (ver_str.startswith("^") and not re.search(r"\d+\.\d+\.\d+", ver_str)):
                    findings.append(
                        CapabilitySignal(
                            capability="unpinned", category="Supply Chain",
                            severity="low", file=source.relative, line=1,
                            code=f'"{pkg}": "{ver_str}"',
                            message=f"npm 依赖未固定版本：{pkg}@{ver_str}。建议固定到具体版本。",
                            is_test=source.is_test, confidence=0.9,
                        )
                    )
    return findings


def _check_osv(findings: list[CapabilitySignal], source: SourceFile, lineno: int, dep_line: str, ecosystem: str) -> None:
    """在线查询 OSV API 已知漏洞（best-effort，失败静默）。"""
    try:
        import urllib.request
        m = re.match(r"([A-Za-z0-9_.-]+)\s*==\s*([\d.]+)", dep_line)
        if not m:
            return
        pkg_name, version = m.group(1), m.group(2)
        payload = json.dumps(
            {"package": {"ecosystem": ecosystem, "name": pkg_name}, "version": version}
        ).encode()
        req = urllib.request.Request(
            "https://api.osv.dev/v1/query",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        vulns = data.get("vulns", [])
        if vulns:
            ids = ", ".join(v["id"] for v in vulns[:10])
            findings.append(
                CapabilitySignal(
                    capability="cve", category="Known Vulnerable Dependency",
                    severity="high", file=source.relative, line=lineno,
                    code=dep_line[:220],
                    message=f"{pkg_name}=={version} 存在 {len(vulns)} 个已知漏洞：{ids}",
                    is_test=source.is_test, confidence=0.93,
                )
            )
    except Exception:
        # 网络失败/超时静默跳过，不影响离线结果
        pass


# ---------------------------------------------------------------------------
# 文档披露检查（Missing User Warnings / MCP Least Privilege / Context-Inappropriate）
# ---------------------------------------------------------------------------

def _scan_disclosure(sources: list[SourceFile], capabilities: list[CapabilitySignal]) -> list[CapabilitySignal]:
    doc_texts: list[str] = []
    for source in sources:
        if source.is_public_doc:
            doc_texts.append(source.relative + "\n" + source.text)
    combined_docs = "\n".join(doc_texts)

    # 轻量描述信号（来自 SKILL.md description 与正文开头）
    skill_md = next((s for s in sources if s.relative == "SKILL.md"), None)
    description_text = skill_md.text if skill_md else ""
    frontmatter_desc = ""
    m = re.search(r"description:\s*(.+)", description_text)
    if m:
        frontmatter_desc = m.group(1)

    lightweight_hit = any(kw in (description_text[:2000] + frontmatter_desc) for kw in LIGHTWEIGHT_SIGNALS)

    # 权限声明章节是否存在
    has_permission_section = any(kw in combined_docs for kw in PERMISSION_SECTION_KEYWORDS)

    # 去重：按 capability 统计代码中实际出现的能力
    present_capabilities: dict[str, list[CapabilitySignal]] = {}
    for c in capabilities:
        if c.is_test:
            continue
        if c.capability in {
            "secret", "prompt_injection", "syntax_error", "cve", "unpinned",
            "scope_creep", "taint", "unicode", "enumerate", "mcp_wildcard",
        }:
            continue
        present_capabilities.setdefault(c.capability, []).append(c)

    findings: list[CapabilitySignal] = []
    for capability, signals in present_capabilities.items():
        keywords = DISCLOSURE_KEYWORDS.get(capability, [])
        disclosed = any(kw in combined_docs for kw in keywords)
        if not disclosed:
            first = signals[0]
            findings.append(
                CapabilitySignal(
                    capability="disclosure", category="Missing User Warnings",
                    severity="medium", file=first.file, line=first.line,
                    code=first.code,
                    message=f"检测到 {capability} 能力（{len(signals)} 处，如 {first.file}:{first.line}）"
                            f"但 SKILL.md/README/references 未披露该能力的行为与风险。"
                            f"建议补充说明，避免用户或 Agent 在不知情时触发网络请求/执行/安装。",
                    is_test=False, confidence=0.9,
                )
            )

    # MCP Least Privilege：有能力但 SKILL.md 无权限声明章节
    if present_capabilities and not has_permission_section:
        if skill_md is not None:
            findings.append(
                CapabilitySignal(
                    capability="permission", category="MCP Least Privilege",
                    severity="medium", file="SKILL.md", line=1,
                    code="",
                    message="SKILL.md 未声明所需权限/能力边界（网络、代码执行、文件访问、环境变量等）。"
                            f"检测到能力：{', '.join(sorted(present_capabilities))}。"
                            "应在 SKILL.md 增加'所需权限与安全说明'章节。",
                    is_test=False, confidence=0.91,
                )
            )

    # Context-Inappropriate Capability：轻量描述 + 未披露的重型能力（network/install/browser）
    heavy_capabilities = [c for c in present_capabilities if c in {"network", "install", "browser"}]
    undisclosed_heavy = [
        c for c in heavy_capabilities
        if not any(kw in combined_docs for kw in DISCLOSURE_KEYWORDS[c])
    ]
    if lightweight_hit and undisclosed_heavy:
        first_signal = present_capabilities[undisclosed_heavy[0]][0]
        findings.append(
            CapabilitySignal(
                capability="context_mismatch", category="Context-Inappropriate Capability",
                severity="medium", file=first_signal.file, line=first_signal.line,
                code=first_signal.code,
                message=f"SKILL.md 描述偏'简单/转换/轻量'（含 {frontmatter_desc.strip()[:40] or '轻量信号'}），"
                        f"但代码含未披露的重型能力：{', '.join(undisclosed_heavy)}。"
                        "能力超出描述语境，需声明必要性或默认关闭。",
                is_test=False, confidence=0.85,
            )
        )
    return findings


# ---------------------------------------------------------------------------
# Scope Creep / Description-Behavior Mismatch（文档级）
# ---------------------------------------------------------------------------

# 高风险动作：类别 -> {patterns（在文档中出现的动作表述）, excused_by（技能宣称用途中
# 提到这些词时视为已披露、不判 mismatch）}
# 只保留"具体指令式动作"，避免把依赖安装说明、安全文档里的概念性描述（如"webhook""外传"）
# 误判为 scope creep；依赖安装与网络外传已由 install/network 能力检测覆盖。
HIGH_IMPACT_ACTIONS = {
    "publish": {
        "patterns": [
            r"clawhub\s+publish",
            r"(?:npm|npx|pnpm|yarn)\s+publish",
            r"发布到|执行发布|进行发布|触发发布|自动发布",
            r"\bpublish\s+[^\s]",
        ],
        "excused_by": [
            "发布", "publish", "同步", "上传", "部署", "分发", "sync", "deploy",
            "clawhub", "市场", "marketplace", "共享", "share",
        ],
    },
    "repo_mutation": {
        "patterns": [
            r"sync-allowlist", r"\ballowlist\b", r"force-push", r"filter-repo", r"重写历史",
        ],
        "excused_by": [
            "同步", "发布", "publish", "sync", "allowlist", "白名单", "clawhub",
            "市场", "marketplace",
        ],
    },
}


def _extract_purpose_text(sources: list[SourceFile]) -> str:
    """从 SKILL.md 提取技能宣称用途（frontmatter description + 标题 + 正文开头）。"""
    skill_md = next((s for s in sources if s.relative == "SKILL.md"), None)
    if not skill_md:
        return ""
    text = skill_md.text
    parts: list[str] = []
    m = re.search(r"^description:\s*(.+)$", text, re.MULTILINE)
    if m:
        parts.append(m.group(1))
    m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if m:
        parts.append(m.group(1))
    parts.append(text[:1500])
    return " ".join(parts).lower()


def _scan_scope_creep(sources: list[SourceFile]) -> list[CapabilitySignal]:
    """文档级 scope creep：宣称用途是本地/低影响力操作，但 SKILL.md/references 引导执行
    未披露的高风险动作（发布/仓库状态变更/提权/外传），对应 SkillSpector 的
    Description-Behavior Mismatch / Context-Inappropriate Capability。"""
    purpose = _extract_purpose_text(sources)
    findings: list[CapabilitySignal] = []
    if not purpose:
        return findings

    for source in sources:
        if not source.is_public_doc:
            continue
        for lineno, line in enumerate(source.lines, 1):
            lowered = line.lower()
            for category, rule in HIGH_IMPACT_ACTIONS.items():
                # 宣称用途已提到该类别 -> 已披露
                if any(k in purpose for k in rule["excused_by"]):
                    continue
                for pattern in rule["patterns"]:
                    if re.search(pattern, line, re.IGNORECASE):
                        sev = "high" if category == "publish" else "medium"
                        findings.append(
                            CapabilitySignal(
                                capability="scope_creep", category="Description-Behavior Mismatch",
                                severity=sev, file=source.relative, line=lineno,
                                code=line.strip()[:220],
                                message=f"检测到'{category}'类高风险动作（{pattern}），"
                                        f"但技能宣称用途（{purpose[:40]}...）未披露该能力。"
                                        "用户调用本技能时可能意外触发发布/仓库变更/提权/外传，需在文档披露或移除。",
                                is_test=source.is_test, confidence=0.8,
                            )
                        )
                        break
    return findings


# ---------------------------------------------------------------------------
# Taint Tracking（文件内数据流：env/argv/input/network/file -> subprocess）
# ---------------------------------------------------------------------------

def _collect_taint_ast(source: SourceFile) -> list[CapabilitySignal]:
    """简化流不敏感污点分析：追踪外部来源变量是否流入 subprocess 命令/参数。
    对应 SkillSpector 的 Taint Tracking（如 os.environ.get -> subprocess.run）。"""
    findings: list[CapabilitySignal] = []
    try:
        tree = ast.parse(source.text)
    except SyntaxError:
        return findings

    # name -> 污点来源标签（env/argv/input/network/file）；一旦污染则保持（sticky）
    tainted: dict[str, str] = {}

    def is_taint_source(expr: ast.AST) -> str | None:
        if isinstance(expr, ast.Call):
            base, chain = _resolve_call_base(expr.func)
            fname = getattr(expr.func, "attr", None) or getattr(expr.func, "id", None)
            if base == "os" and chain in {"get", "getenv", "environ.get"}:
                return "env"
            if base == "sys" and chain.startswith("argv"):
                return "argv"
            if fname == "input":
                return "input"
            if fname == "open":
                return "file"
            if base in {"requests", "urllib", "httpx", "aiohttp", "socket", "websocket"}:
                return "network"
        if isinstance(expr, ast.Subscript):
            base, chain = _resolve_call_base(expr.value)
            if base == "os" and chain == "environ":
                return "env"
            if base == "sys" and chain == "argv":
                return "argv"
        return None

    def expr_taint(expr: ast.AST) -> str | None:
        if isinstance(expr, ast.Name):
            return tainted.get(expr.id)
        if isinstance(expr, ast.Constant):
            return None
        if isinstance(expr, ast.Call):
            src = is_taint_source(expr)
            if src:
                return src
            # .strip()/.replace()/.format()/os.path.join() 等在污染值上的方法调用
            if isinstance(expr.func, ast.Attribute):
                base, chain = _resolve_call_base(expr.func)
                if chain in {"strip", "replace", "lower", "upper", "format", "lstrip", "rstrip", "split", "get"}:
                    return expr_taint(expr.func.value)
                if chain in {"path.join", "abspath", "normpath", "realpath"} or chain.startswith("path."):
                    return next((expr_taint(a) for a in expr.args if expr_taint(a)), None)
            return None
        if isinstance(expr, ast.BinOp):
            return expr_taint(expr.left) or expr_taint(expr.right)
        if isinstance(expr, ast.BoolOp):
            return next((expr_taint(v) for v in expr.values if expr_taint(v)), None)
        if isinstance(expr, ast.IfExp):  # A if cond else B
            return expr_taint(expr.body) or expr_taint(expr.orelse)
        if isinstance(expr, (ast.List, ast.Tuple)):
            return next((expr_taint(el) for el in expr.elts if expr_taint(el)), None)
        if isinstance(expr, (ast.Attribute, ast.Subscript)):
            return expr_taint(expr.value)
        return None

    # 第一遍：收集赋值污点（流不敏感近似，顺序遍历）
    for node in ast.walk(tree):
        targets: list[ast.AST] = []
        value = None
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target]
            value = node.value
        elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
            targets = [node.target]
            value = None
        if value is None:
            continue
        src = expr_taint(value)
        for target in targets:
            if isinstance(target, ast.Name):
                if src:
                    tainted[target.id] = src
                # src 为 None 时保持已有污点（sticky），避免被无害重赋值抹掉

    # 第二遍：subprocess 调用参数检查
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        base, chain = _resolve_call_base(node.func)
        fname = getattr(node.func, "attr", None)
        if not (base == "subprocess" and fname in SUBPROCESS_NAMES):
            continue
        if not node.args:
            continue
        first = node.args[0]
        hits: list[tuple[str, str]] = []
        if isinstance(first, (ast.List, ast.Tuple)):
            for el in first.elts:
                src = expr_taint(el)
                if src:
                    hits.append((src, ast.get_source_segment(source.text, el) or ""))
        else:
            src = expr_taint(first)
            if src:
                hits.append((src, ast.get_source_segment(source.text, first) or ""))
        for src, seg in hits:
            findings.append(
                CapabilitySignal(
                    capability="taint", category="Taint Tracking",
                    severity="medium", file=source.relative, line=getattr(node, "lineno", 1),
                    code=ast.get_source_segment(source.text, node) or "",
                    message=f"污点流：来自 '{src}' 的值流入 subprocess.{fname} 命令/参数（{seg[:60]}）。"
                            "若输入来自外部不可信源，存在命令注入/参数注入风险。",
                    is_test=source.is_test, confidence=0.7,
                )
            )
    return findings


# ---------------------------------------------------------------------------
# Unicode Deception / 隐藏字符
# ---------------------------------------------------------------------------

UNICODE_DECEPTION_CHARS = {
    "\u200b": ("零宽空格 ZWSP", "200B"),
    "\u200c": ("零宽非连接符 ZWNJ", "200C"),
    "\u200d": ("零宽连接符 ZWJ", "200D"),
    "\ufeff": ("零宽无断空格 BOM", "FEFF"),
    "\u202a": ("LTR 嵌入", "202A"),
    "\u202b": ("RTL 嵌入", "202B"),
    "\u202c": ("POP 方向格式化", "202C"),
    "\u202d": ("LTR 覆盖", "202D"),
    "\u202e": ("RTL 覆盖", "202E"),
    "\u2066": ("LTR 隔离", "2066"),
    "\u2067": ("RTL 隔离", "2067"),
    "\u2068": ("首选项隔离", "2068"),
    "\u2069": ("隔离结束", "2069"),
}


def _scan_unicode_deception(sources: list[SourceFile]) -> list[CapabilitySignal]:
    """扫描零宽字符/RTL 覆盖等隐藏字符，可用于隐藏指令或欺骗标识符。
    U+200D（ZWJ）在 emoji 序列（如 👨\u200d💼）中是合法用法，行内含 emoji 时跳过。"""
    findings: list[CapabilitySignal] = []
    EMOJI_RE = re.compile(r"[\U0001F000-\U0001FAFF\u2600-\u27BF]")
    for source in sources:
        for lineno, line in enumerate(source.lines, 1):
            has_emoji = bool(EMOJI_RE.search(line))
            for ch, (name, codepoint) in UNICODE_DECEPTION_CHARS.items():
                if ch not in line:
                    continue
                if codepoint == "200D" and has_emoji:
                    continue  # emoji ZWJ 序列，合法
                findings.append(
                    CapabilitySignal(
                        capability="unicode", category="Unicode Deception",
                        severity="medium", file=source.relative, line=lineno,
                        code=line.strip()[:220],
                        message=f"检测到隐藏 Unicode 字符（{name}，U+{codepoint}），"
                                "可用于隐藏指令、欺骗标识符或静默改变语义。",
                        is_test=source.is_test, confidence=0.9,
                    )
                )
                break
    return findings


# ---------------------------------------------------------------------------
# 文件系统枚举（扫描用户主目录/敏感目录）
# ---------------------------------------------------------------------------

def _collect_fs_enumeration_ast(source: SourceFile) -> list[CapabilitySignal]:
    findings: list[CapabilitySignal] = []
    try:
        tree = ast.parse(source.text)
    except SyntaxError:
        return findings

    ENUM_SENSITIVE_RE = re.compile(
        r"expanduser|['\"](?:~|/Users/|/home/|/etc/|/root)|\.ssh|\.aws|\.gnupg|\.env|/Users/",
        re.IGNORECASE,
    )
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        base, chain = _resolve_call_base(node.func)
        fname = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
        is_enum = (
            (base == "os" and fname in {"walk", "listdir", "scandir"})
            or (base == "glob" and fname in {"glob", "iglob"})
            or (base == "pathlib" and fname == "glob")
        )
        if not is_enum:
            continue
        seg = ast.get_source_segment(source.text, node) or ""
        if ENUM_SENSITIVE_RE.search(seg):
            findings.append(
                CapabilitySignal(
                    capability="enumerate", category="File System Enumeration",
                    severity="medium", file=source.relative, line=getattr(node, "lineno", 1),
                    code=seg[:220],
                    message="递归/枚举目录，且路径涉及用户主目录或敏感目录（~/.ssh/.aws/.env 等），"
                            "可能枚举用户文件系统（对应 SkillSpector File System Enumeration）。",
                    is_test=source.is_test, confidence=0.8,
                )
            )
    return findings


# ---------------------------------------------------------------------------
# MCP 通配权限（最小权限缺口）
# ---------------------------------------------------------------------------

def _scan_mcp_wildcard(sources: list[SourceFile]) -> list[CapabilitySignal]:
    findings: list[CapabilitySignal] = []
    for source in sources:
        name = source.relative.lower()
        is_mcp_file = (
            name.endswith("mcp.json")
            or name.endswith("mcp-servers.json")
            or name.endswith(".mcp.json")
            or (name.endswith(".json") and "mcp" in name)
        )
        if not is_mcp_file:
            continue
        for lineno, line in enumerate(source.lines, 1):
            if re.search(r'["\']?\*["\']?', line) and re.search(r"tools|permissions|resources|scopes", line, re.IGNORECASE):
                findings.append(
                    CapabilitySignal(
                        capability="mcp_wildcard", category="MCP Least Privilege",
                        severity="medium", file=source.relative, line=lineno,
                        code=line.strip()[:220],
                        message="MCP 配置出现通配符权限（*），未按最小权限声明工具/资源/作用域边界"
                                "（对应 SkillSpector Wildcard Permission）。",
                        is_test=source.is_test, confidence=0.85,
                    )
                )
    return findings


# ---------------------------------------------------------------------------
# 汇总与报告
# ---------------------------------------------------------------------------

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def _dedup_findings(findings: list[CapabilitySignal]) -> list[CapabilitySignal]:
    """按 (capability, file, line, code, severity) 去重；测试文件中的危险模式降级为提示。"""
    seen: set[tuple] = set()
    unique: list[CapabilitySignal] = []
    for f in sorted(findings, key=lambda x: (SEVERITY_ORDER.get(x.severity, 9), x.file, x.line)):
        key = (f.capability, f.file, f.line, f.code[:80], f.severity)
        if key in seen:
            continue
        seen.add(key)
        # 测试文件中的 supply-chain / 危险执行 / 权限提升通常是防护样例或 fixture，非交付行为
        if f.is_test and f.severity in {"critical", "high"} and f.capability in {
            "install", "privilege", "subprocess", "dynamic_import", "secret", "prompt_injection",
            "taint", "enumerate", "unicode", "mcp_wildcard",
        }:
            f = CapabilitySignal(
                capability=f.capability, category=f.category,
                severity="medium", file=f.file, line=f.line, code=f.code,
                message=f.message + "（位于测试文件，判定为防护/示例 fixture，非交付行为）",
                is_test=f.is_test, confidence=f.confidence,
            )
        unique.append(f)
    return unique


def scan_candidate(candidate_root: Path, online: bool = False) -> dict[str, Any]:
    candidate_root = candidate_root.expanduser().resolve()
    skill_md = candidate_root / "SKILL.md"
    if not skill_md.is_file():
        raise ValueError(f"未发现 SKILL.md: {candidate_root}")

    sources = _read_sources(candidate_root)
    findings: list[CapabilitySignal] = []

    for source in sources:
        if source.path.suffix in PY_SUFFIXES:
            findings.extend(_collect_capabilities_ast(source))
            findings.extend(_collect_taint_ast(source))
            findings.extend(_collect_fs_enumeration_ast(source))
        elif source.path.suffix in SH_SUFFIXES:
            findings.extend(_collect_capabilities_shell(source))
        if source.path.name in DEP_FILE_NAMES:
            findings.extend(_scan_dependencies(source, online))

    findings.extend(_scan_hardcoded_secrets(sources))
    findings.extend(_scan_prompt_injection(sources))
    findings.extend(_scan_unicode_deception(sources))
    findings.extend(_scan_mcp_wildcard(sources))
    findings.extend(_scan_scope_creep(sources))
    findings.extend(_scan_disclosure(sources, findings))

    findings = _dedup_findings(findings)

    critical = sum(1 for f in findings if f.severity == "critical")
    high = sum(1 for f in findings if f.severity == "high")
    medium = sum(1 for f in findings if f.severity == "medium")
    low = sum(1 for f in findings if f.severity == "low")
    info = sum(1 for f in findings if f.severity == "info")

    status = "FAIL" if (critical or high) else ("WARN" if (medium or low) else "PASS")
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "audit",
        "candidate_root": str(candidate_root),
        "status": status,
        "summary": {
            "critical": critical,
            "high": high,
            "medium": medium,
            "low": low,
            "info": info,
            "total": len(findings),
            "skills": 1,
        },
        "findings": [f.to_dict() for f in findings],
    }


def scan_collection(collection_root: Path, online: bool = False) -> dict[str, Any]:
    collection_root = collection_root.expanduser().resolve()
    roots = _discover_skill_roots(collection_root)
    if not roots:
        raise ValueError(f"集合中未发现任何 SKILL.md: {collection_root}")
    reports = []
    for root in roots:
        try:
            reports.append(scan_candidate(root, online=online))
        except ValueError as exc:
            reports.append(
                {
                    "schema_version": SCHEMA_VERSION,
                    "mode": "audit",
                    "candidate_root": str(root),
                    "status": "ERROR",
                    "summary": {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0, "total": 0, "skills": 0},
                    "error": str(exc),
                    "findings": [],
                }
            )
    totals = {
        "skills": len(reports),
        "failed_skills": sum(r["status"] == "FAIL" for r in reports),
        "warning_skills": sum(r["status"] == "WARN" for r in reports),
        "critical": sum(r["summary"]["critical"] for r in reports),
        "high": sum(r["summary"]["high"] for r in reports),
        "medium": sum(r["summary"]["medium"] for r in reports),
        "low": sum(r["summary"]["low"] for r in reports),
        "info": sum(r["summary"]["info"] for r in reports),
        "total": sum(r["summary"]["total"] for r in reports),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "batch",
        "collection_root": str(collection_root),
        "status": "FAIL" if totals["failed_skills"] else ("WARN" if totals["warning_skills"] else "PASS"),
        "summary": totals,
        "skills": reports,
    }


def _write_output(report: dict[str, Any], output: str | None) -> None:
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if output:
        path = Path(output).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(encoded, encoding="utf-8")
    sys.stdout.write(encoded)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit_parser = subparsers.add_parser("audit", help="审查单个 Skill")
    audit_parser.add_argument("--candidate-root", required=True)
    audit_parser.add_argument("--output")
    audit_parser.add_argument("--online", action="store_true", help="联网查询 OSV 已知漏洞（默认离线）")

    batch_parser = subparsers.add_parser("batch", help="递归审查 Skill 集合")
    batch_parser.add_argument("--root", required=True)
    batch_parser.add_argument("--output")
    batch_parser.add_argument("--online", action="store_true", help="联网查询 OSV 已知漏洞（默认离线）")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "audit":
            report = scan_candidate(Path(args.candidate_root), online=args.online)
        else:
            report = scan_collection(Path(args.root), online=args.online)
    except ValueError as exc:
        print(f"❌ 范围错误: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"❌ 扫描失败: {exc}", file=sys.stderr)
        return 2

    _write_output(report, args.output)
    if args.command == "audit":
        return 1 if report["status"] == "FAIL" else 0
    return 1 if report["status"] == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
