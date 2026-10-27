#!/usr/bin/env python3
"""
Timeline Dream Sweep for Self Evolve.

This script scans Claude Code and Codex session records, builds lightweight
session summaries, clusters related long-running work, and optionally publishes
sanitized deterministic packets into the external Review Inbox.

It does not modify mature Skills, user context, or project context.
"""

from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import os
import re
import shutil
import sys
import tempfile
import time
from collections import Counter, defaultdict, deque
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX fallback
    fcntl = None

from privacy_gate import evidence_id, sanitize_text, write_review_artifact
from self_evolve_paths import RAW_SESSIONS_DIR, REVIEW_INBOX_ROOT, RUNTIME_ROOT, SKILL_ROOT, assert_runtime_ready


CORE_SKILLS_PATH = SKILL_ROOT / "config" / "core_skills.yaml"

SESSION_SUMMARY_DIR = RUNTIME_ROOT / "session-summaries"
DREAMING_DIR = RUNTIME_ROOT / "dreaming"
DREAM_RUN_DIR = DREAMING_DIR / "runs"
BACKFILL_STATE_PATH = DREAMING_DIR / "backfill-state.json"
TIMELINE_OUTPUT_DIR = REVIEW_INBOX_ROOT / "timeline"
DREAM_OUTPUT_DIR = REVIEW_INBOX_ROOT / "cluster-packets"
DEFAULT_MAX_CLUSTER_SIZE = 24
CLUSTER_ID_SCHEMA = "topic-cluster-v2"
LEGACY_MEMBER_BOUND_CLUSTER_ID = re.compile(
    r"^clu-(?P<semantic>[0-9a-f]{8})-(?P<members>[0-9a-f]{12})-(?P<slug>.+)$"
)
STABLE_CLUSTER_ID = re.compile(
    r"^clu-(?P<semantic>[0-9a-f]{16})-(?P<lineage>[0-9a-f]{64})-(?P<slug>.+)$"
)


SESSION_CLASS_POLICY = {
    "substantive": "summarize_candidate",
    "meta_design": "summarize_candidate",
    "article_signal": "cluster_candidate",
    "tooling_fix": "aggregate_only",
    "maintenance": "index_only",
    "git_ops": "index_only",
    "software_update": "index_only",
    "machine_generated": "skip",
}

METHOD_SIGNAL_PHRASES = [
    "方法论",
    "工作流",
    "检查清单",
    "模板",
    "命名规范",
    "评估闭环",
    "沉淀标准",
    "自动化",
    "程序化",
    "复用",
    "验收",
    "边界",
    "人机协作",
    "人在回路",
]

USER_INTENT_PHRASES = [
    "沉淀",
    "写进 skill",
    "写到 skill",
    "以后按",
    "记住",
    "升级建议",
    "文章草稿",
    "公众号",
    "初稿",
    "复盘",
    "后续更新",
]

META_DESIGN_PHRASES = [
    "self-evolve",
    "skill-evolve",
    "Self Evolve",
    "Skill Evolve",
    "Timeline Dream Sweep",
    "Dream Sweep",
    "dream_sweep",
    "SessionEnd",
    "session end",
    "headless",
    "hook",
    "hooks",
    "评估闭环",
    "候选记录",
    "run now",
    "scheduled_tasks",
    "scheduler_run",
    "launchd",
    "面板",
    "Review Inbox",
]

ARTICLE_PHRASES = [
    "文章",
    "公众号",
    "知乎",
    "初稿",
    "发布",
    "标题",
    "复盘",
    "写作",
    "素材",
    "实战",
    "测试",
    # 写作意图词（v1.1.3）：明确"要写下来/分享"的信号，非泛技术词
    "设计手记",
    "长文",
    "写一篇",
    "记录成文",
    "分享出来",
    "发出来",
]

SUBSTANTIVE_PHRASES = [
    "法律",
    "案件",
    "诉讼",
    "证据",
    "侵权",
    "著作权",
    "商标",
    "专利",
    "合同",
    "OCR",
    "录屏",
    "截图",
    "抽帧",
    "视频",
    "MiniMax",
    "M3",
    "skill",
    "Skill",
    "工作流",
]

TOOLING_PHRASES = [
    "报错",
    "失败",
    "bug",
    "修复",
    "排查",
    "路径",
    "hook 丢失",
    "不生效",
    "构建",
    "测试失败",
    "验证失败",
    "权限",
    "timeout",
    "failed",
    "error",
]

GIT_PHRASES = [
    "git status",
    "git add",
    "git commit",
    "git push",
    "git pull",
    "git merge",
    "git rebase",
    "subtree",
    "PR",
    "pull request",
    "tag",
    "提交",
    "推送",
]

MAINTENANCE_PHRASES = [
    "brew install",
    "brew upgrade",
    "npm install",
    "pip install",
    "更新软件",
    "安装依赖",
    "环境变量",
    "配置环境",
    "清理缓存",
    "同步仓库",
]

SOFTWARE_UPDATE_PHRASES = [
    "更新 Claude",
    "更新 Codex",
    "Claude Code 更新",
    "Codex 更新",
    "升级 Claude",
    "升级 Codex",
    "homebrew upgrade",
]

MACHINE_MARKERS = [
    "SE_EXTRACTION",
    "LKE_EXTRACTION",
    "SELF_EVOLVE_HEADLESS",
    "SKILL_EVOLVE_HEADLESS",
    "Self Evolve 的独立 headless 分析 session",
]

GENERIC_SKILL_KEYWORDS = {
    "建议",
    "升级",
    "文章",
    "公众号",
    "案件",
    "阶段",
    "PDF",
    "证据",
    "法律",
    "测试",
    "沉淀",
    "skill",
    "Skill",
    "复盘",
    "方法论",
}

GENERIC_TOPIC_TERMS = GENERIC_SKILL_KEYWORDS | {
    "工作流",
    "模板",
    "复用",
    "标题",
    "实战",
    "验证",
    "工具",
    "article_draft",
    "verification",
    "workflow_design",
    "skill_patch",
    "unknown",
    "legal-skills",
    "private-skills",
    "skills",
}

SENSITIVE_PATTERNS = [
    ("case_number", re.compile(r"[（(]\d{4}[）)][\u4e00-\u9fa5A-Za-z0-9第初终再执民刑行知商破保管辖号字\-]+号")),
    ("mobile", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("id_card", re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")),
    ("tsa_id", re.compile(r"\bTSA[-_A-Za-z0-9]{6,}\b")),
    ("price", re.compile(r"(?<!\w)(?:¥|￥)?\d+(?:\.\d+)?\s*(?:元|万元|万|RMB|人民币)(?!\w)")),
    ("company_name", re.compile(r"[\u4e00-\u9fa5]{2,40}(?:有限责任公司|有限公司|商贸有限公司|餐饮管理有限公司)")),
    ("vs_parties", re.compile(r"[\u4e00-\u9fa5A-Za-z]{2,12}\s*vs\s*[\u4e00-\u9fa5A-Za-z0-9]{2,30}", re.IGNORECASE)),
]

CONTEXT_NOISE_MARKERS = [
    "# AGENTS.md instructions",
    "<INSTRUCTIONS>",
    "<permissions instructions>",
    "<app-context>",
    "<skills_instructions>",
    "<plugins_instructions>",
    "<environment_context>",
    "<command-message>",
    "<command-name>",
    "Context Usage",
    "Base directory for this skill:",
    "Shell cwd was reset",
    "AI-SUMMARY:START",
    "<system-reminder>",
    "<CRON_TASK",
    "<observed_from_primary_session",
    "<what_happened>",
    "<occurred_at>",
    "<subagent_notification>",
    "<turn_aborted>",
    "<heartbeat>",
    "<send_user_message_question_reply>",
    "<task-notification>",
    "You are working inside Orca, a multi-agent IDE.",
    "Caveat: The messages below were generated by the user",
]

REPORT_NOISE_MARKERS = [
    "<tool_use_error>",
    "Launching skill:",
    "Permission for this action was denied",
    "File content (",
    "exceeds maximum allowed size",
    "npm ERR!",
    "bfs: error:",
    "Traceback (most recent call last)",
    "ModuleNotFoundError",
    "ImportError",
    "Exit code:",
    "rmdir:",
    "ls:",
    "Directory not empty",
    "file state is current",
    "has been updated successfully",
    "The file ",
    "Task #",
    "总页数:",
    "第 1 页",
    "答辩状",
    "注册地址",
    "法定代表人",
    "关键风险与提醒",
    "持续侵权",
    "人民法院",
    "送达文书",
    "点击链接查阅",
    "ffmpeg -i",
    "```bash",
    "**输出**",
    "Your questions have been answered",
    "Updated task #",
    "homepage: pending",
    "# Files mentioned by the user",
    "codex-clipboard",
    "/var/folders",
    "SyntaxError:",
    "Is this intended to be part of the string",
    "位于分支",
    "尚未暂存",
    "=== ",
    "<system-reminder>",
    "<CRON_TASK",
    "<observed_from_primary_session",
    "<what_happened>",
    "<occurred_at>",
]


@dataclass
class SessionSummary:
    source: str
    source_variant: str
    session_id: str
    transcript_path: str
    started_at: str
    ended_at: str
    cwd: str
    cwd_label: str
    agent_context: dict[str, Any]
    topic_title: str
    topic_keywords: list[str]
    session_class: str
    summary_policy: str
    noise_reasons: list[str]
    related_skills: list[str]
    work_stage: str
    agent_collaboration_mode: str
    decisions: list[str]
    open_questions: list[str]
    upgrade_signals: list[str]
    article_signals: list[str]
    timeline_signals: list[str]
    sensitive_risk: bool
    redaction_notes: list[str]
    evidence_snippets: list[str]
    transcript_mtime: float = 0
    transcript_size: int = 0
    transcript_fingerprint: str = ""
    read_strategy: str = "stream_head_key_tail"
    total_line_count: int = 0
    parsed_line_count: int = 0
    invalid_line_count: int = 0
    selected_line_count: int = 0
    skipped_line_count: int = 0
    selected_record_count: int = 0
    skipped_oversized_tool_lines: int = 0
    skipped_oversized_lines: int = 0
    promoted: bool = False
    skipped_reason: str = ""


@dataclass
class TopicCluster:
    cluster_id: str
    title: str
    sessions: list[SessionSummary] = field(default_factory=list)
    topic_key: str = ""
    semantic_digest: str = ""
    member_digest: str = ""
    revision: str = ""
    legacy_cluster_ids: list[str] = field(default_factory=list)
    topic_keywords: list[str] = field(default_factory=list)
    related_skills: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    work_stages: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    score: int = 0
    cohesion_average: float = 0.0
    cohesion_minimum: float = 0.0
    purity: float = 0.0
    uncertainty: float = 1.0
    quality_gate: str = "observe_only"


@dataclass(frozen=True)
class SourceTranscript:
    source: str
    source_variant: str
    path: Path


@dataclass(frozen=True)
class JsonlReadStats:
    total_lines: int = 0
    parsed_lines: int = 0
    selected_lines: int = 0
    invalid_lines: int = 0
    skipped_oversized_tool_lines: int = 0
    skipped_oversized_lines: int = 0


def now_stamp() -> str:
    return time.strftime("%y%m%d")


def run_stamp() -> str:
    return time.strftime("%y%m%d_%H%M%S")


def safe_slug(value: str, default: str = "topic") -> str:
    text = re.sub(r"\s+", "-", value.strip())
    text = re.sub(r"[^A-Za-z0-9_\-\u4e00-\u9fff]+", "", text)
    text = text.strip("-_")
    return text[:60] or default


def parse_since(raw: str) -> timedelta | None:
    if (raw or "").strip().lower() == "all":
        return None
    match = re.match(r"^\s*(\d+)\s*([dhw])\s*$", raw or "")
    if not match:
        raise SystemExit("--since 需要形如 7d、14d、24h、2w 或 all")
    value = int(match.group(1))
    unit = match.group(2)
    if unit == "h":
        return timedelta(hours=value)
    if unit == "w":
        return timedelta(days=value * 7)
    return timedelta(days=value)


def parse_time(raw: Any) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        # Codex event_msg started_at sometimes stores epoch seconds.
        try:
            return datetime.fromtimestamp(float(raw), tz=timezone.utc)
        except (OSError, ValueError):
            return None
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    if not value:
        return None
    if value.endswith("Z"):
        value = f"{value[:-1]}+00:00"
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def format_dt(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def date_key(dt_raw: str) -> str:
    dt = parse_time(dt_raw)
    if dt:
        return dt.astimezone().strftime("%Y-%m-%d")
    return dt_raw[:10] if dt_raw else ""


def _looks_like_tool_line(raw: bytes) -> bool:
    sample = raw[:8192].lower()
    return any(
        marker in sample
        for marker in (
            b'"type":"tool_result"',
            b'"type": "tool_result"',
            b'"type":"function_call_output"',
            b'"type": "function_call_output"',
            b'"tool_use_id"',
        )
    )


def _record_importance(record: dict[str, Any]) -> int:
    """Score semantically useful records without trusting their content."""
    record_type = str(record.get("type") or "")
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    message = record.get("message") if isinstance(record.get("message"), dict) else {}
    payload_type = str(payload.get("type") or "")
    role = str(payload.get("role") or message.get("role") or "")
    marker = f"{record_type} {payload_type} {role}".lower()
    if any(item in marker for item in ("final", "verification", "completed", "summary")):
        return 6
    if record_type in {"session_meta", "turn_context"}:
        return 5
    if role == "user" or payload_type == "user_message" or record_type == "user":
        return 5
    if role == "assistant" or record_type == "assistant":
        return 4
    if record_type in {"event_msg", "response_item"}:
        return 2
    return 1


def _stable_line_rank(line_number: int, record: dict[str, Any]) -> int:
    identity = record.get("id") or record.get("uuid")
    payload = record.get("payload")
    if isinstance(payload, dict):
        identity = identity or payload.get("id") or payload.get("call_id")
    raw = f"{line_number}\0{identity or ''}\0{record.get('type', '')}".encode()
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")


def read_jsonl_with_stats(
    path: Path,
    max_lines: int = 5000,
    *,
    max_tool_line_bytes: int = 2 * 1024 * 1024,
) -> tuple[list[dict[str, Any]], JsonlReadStats]:
    """Stream JSONL and retain a bounded head/key/tail sample.

    The implementation never calls ``read_text`` on the transcript. Oversized
    tool-result lines are discarded before JSON decoding, while ordinary final
    messages remain eligible for the tail window regardless of their position.
    """
    limit = max(1, int(max_lines or 1))
    head_limit = max(1, limit // 5)
    tail_limit = max(1, limit // 4)
    key_limit = max(0, limit - head_limit - tail_limit)
    head: list[tuple[int, dict[str, Any]]] = []
    tail: deque[tuple[int, dict[str, Any]]] = deque(maxlen=tail_limit)
    # Min-heap of the strongest deterministic semantic samples.
    key_heap: list[tuple[int, int, int, dict[str, Any]]] = []
    total = parsed = invalid = oversized = generic_oversized = 0

    # 合同（A-F3）：打开失败（权限/IO）向上传播，由调用方按读取失败分类；
    # 不得返回空统计让上层误判为空会话。dream_sweep 的逐会话 except OSError
    # 与 runtime_sessions 的 failed 分类各自兜底。
    handle = path.open("rb")

    with handle:
        line_number = 0
        while True:
            # ``readline(size)`` bounds the allocation even when a producer
            # writes a pathological single line without a newline.
            raw = handle.readline(max_tool_line_bytes + 1)
            if not raw:
                break
            line_number += 1
            total += 1
            line_complete = raw.endswith(b"\n") or len(raw) < max_tool_line_bytes + 1
            if len(raw) > max_tool_line_bytes or not line_complete:
                is_tool = _looks_like_tool_line(raw)
                oversized += int(is_tool)
                # Drain the rest of this physical line in bounded chunks so the
                # next valid JSONL event (often final/verification) is retained.
                while not line_complete:
                    chunk = handle.readline(64 * 1024)
                    if not chunk:
                        line_complete = True
                        break
                    line_complete = chunk.endswith(b"\n")
                generic_oversized += int(not is_tool)
                continue
            stripped = raw.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped.decode("utf-8", errors="replace"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                invalid += 1
                continue
            if not isinstance(record, dict):
                invalid += 1
                continue
            parsed += 1
            item = (line_number, record)
            if len(head) < head_limit:
                head.append(item)
            tail.append(item)
            if key_limit:
                importance = _record_importance(record)
                rank = _stable_line_rank(line_number, record)
                heap_item = (importance, -rank, line_number, record)
                if len(key_heap) < key_limit:
                    heapq.heappush(key_heap, heap_item)
                elif heap_item[:2] > key_heap[0][:2]:
                    heapq.heapreplace(key_heap, heap_item)

    selected_by_line: dict[int, dict[str, Any]] = {}
    for line_number, record in head:
        selected_by_line[line_number] = record
    for _, _, line_number, record in key_heap:
        selected_by_line[line_number] = record
    for line_number, record in tail:
        selected_by_line[line_number] = record
    selected = [selected_by_line[number] for number in sorted(selected_by_line)]
    if len(selected) > limit:
        selected = selected[:head_limit] + selected[-(limit - head_limit) :]
    return selected, JsonlReadStats(
        total_lines=total,
        parsed_lines=parsed,
        selected_lines=len(selected),
        invalid_lines=invalid,
        skipped_oversized_tool_lines=oversized,
        skipped_oversized_lines=generic_oversized,
    )


def read_jsonl(path: Path, max_lines: int = 5000) -> list[dict[str, Any]]:
    """Compatibility wrapper for callers that only need selected records."""
    return read_jsonl_with_stats(path, max_lines=max_lines)[0]


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return default


def transcript_fingerprint(path: Path) -> dict[str, Any]:
    try:
        stat = path.stat()
    except OSError:
        return {"transcript_mtime": 0.0, "transcript_size": 0, "transcript_fingerprint": ""}
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return {"transcript_mtime": 0.0, "transcript_size": 0, "transcript_fingerprint": ""}
    return {
        "transcript_mtime": stat.st_mtime,
        "transcript_size": stat.st_size,
        "transcript_fingerprint": f"sha256:{digest.hexdigest()}",
    }


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError:
        print("缺少依赖: pyyaml", file=sys.stderr)
        print("请运行: pip install pyyaml", file=sys.stderr)
        raise SystemExit(1)

    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"无法读取 YAML: {path}: {exc}", file=sys.stderr)
        raise SystemExit(1)
    return data if isinstance(data, dict) else {}


def redact_sensitive_text(text: str) -> str:
    # The shared gate dynamically recognizes any user's home directory and
    # other common identifiers; no real username or personal folder is encoded.
    redacted, _ = sanitize_text(text)
    replacements = {
        "case_number": "<案号已脱敏>",
        "mobile": "<手机号已脱敏>",
        "email": "<邮箱已脱敏>",
        "id_card": "<证件号已脱敏>",
        "tsa_id": "<TSA编号已脱敏>",
        "price": "<金额已脱敏>",
        "company_name": "<公司名称已脱敏>",
        "vs_parties": "<当事人信息已脱敏>",
    }
    for name, pattern in SENSITIVE_PATTERNS:
        redacted = pattern.sub(replacements.get(name, "<敏感信息已脱敏>"), redacted)
    redacted = re.sub(r"https?://[^\s`，。；)）]+", "<链接已脱敏>", redacted)
    return redacted


def is_context_noise(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return True
    if any(marker in stripped for marker in CONTEXT_NOISE_MARKERS):
        return True
    if stripped.startswith(("---", "```", "{", "[")) and len(stripped) > 400:
        return True
    if len(stripped) > 1200 and stripped.count("\n") > 20:
        return True
    return False


def is_report_noise(text: str) -> bool:
    stripped = (text or "").strip()
    if is_context_noise(stripped):
        return True
    if any(marker in stripped for marker in REPORT_NOISE_MARKERS):
        return True
    if re.search(r"\btotal\s+\d+\b", stripped) and ("drwx" in stripped or "-rw-" in stripped):
        return True
    if len(re.findall(r"\b\d{1,4}:", stripped)) >= 4 and ("def " in stripped or "parser.add_argument" in stripped or "===" in stripped):
        return True
    if re.match(r"^\s*\d+\s+#\s+", stripped):
        return True
    if "name:" in stripped and "version:" in stripped and "description:" in stripped:
        return True
    if re.match(r"^\s*\d{8}\s+\d{2}:\d{2}:\d{2}\s*$", stripped):
        return True
    if re.match(r"^\s*\d+[:：]", stripped) and len(stripped) > 200:
        return True
    if stripped.count(".md") >= 3:
        return True
    if len(re.findall(r"\b\d{1,4}\s+", stripped)) >= 8 and ("##" in stripped or "```" in stripped or "|" in stripped):
        return True
    if len(re.findall(r"\b(?:[A-Za-z0-9_.-]+: )?(?:error|failed|not found|permission denied)\b", stripped, re.IGNORECASE)) >= 2:
        return True
    return False


def detect_sensitive_markers(text: str) -> list[str]:
    markers = []
    for name, pattern in SENSITIVE_PATTERNS:
        if pattern.search(text):
            markers.append(name)
    return markers


def compact_text(value: str, limit: int = 240) -> str:
    text = " ".join((value or "").split())
    text = redact_sensitive_text(text)
    if len(text) > limit:
        return f"{text[:limit]}..."
    return text


def compact_path(path: str) -> str:
    if not path:
        return ""
    try:
        p = Path(path).expanduser()
        home = Path.home()
        parts = list(p.parts)
        if str(p).startswith(str(home)):
            parts = ["~", *p.relative_to(home).parts]
        if len(parts) <= 4:
            return str(Path(*parts)) if parts and parts[0] != "~" else "/".join(parts)
        return "/".join([parts[0], "...", *parts[-2:]])
    except Exception:
        return path[-80:]


def relative_to_root(path: Path) -> str:
    try:
        return str(path.relative_to(SKILL_ROOT))
    except ValueError:
        return compact_path(str(path))


FRAMEWORK_INJECTION_BLOCK = re.compile(
    r"<(system-reminder|CRON_TASK|observed_from_primary_session|what_happened|occurred_at)"
    r"(?:\s[^>]*)?>[\s\S]*?</\1\s*>",
    re.IGNORECASE,
)
FRAMEWORK_INJECTION_TAG = re.compile(
    r"</?(?:system-reminder|CRON_TASK|observed_from_primary_session|what_happened|occurred_at)\b[^>]*>",
    re.IGNORECASE,
)
HOST_CONTEXT_BLOCK = re.compile(
    r"<(in-app-browser-context|external_codex_apps_open_page)\b[^>]*>[\s\S]*?</\1\s*>",
    re.IGNORECASE,
)
HOST_CONTEXT_TAG = re.compile(
    r"</?(?:in-app-browser-context|external_codex_apps_open_page)\b[^>]*>",
    re.IGNORECASE,
)


def strip_framework_injection(text: str) -> str:
    """剥离 harness / MCP / cron 框架注入文本。

    这些片段以 user 角色的 text block 注入（``<system-reminder>``、``<CRON_TASK>``、
    ``<observed_from_primary_session>`` 等），但不是真实用户输入；若不剥离会污染
    ``topic_title`` / ``topic_keywords`` / ``*_signals`` / ``evidence_snippets``。
    """
    if not text:
        return text
    # Host context can share the same user turn with real human words. Remove
    # only the wrapper span so its boilerplate cannot become "user words".
    text = HOST_CONTEXT_BLOCK.sub(" ", text)
    cleaned = FRAMEWORK_INJECTION_BLOCK.sub(" ", text)
    cleaned = FRAMEWORK_INJECTION_TAG.sub(" ", cleaned)
    return cleaned


def has_unclosed_host_context(text: str) -> bool:
    """True unless every host-context tag pair is well-formed and exclusive.

    Runs on the raw user turn, before paired-block stripping: the paired
    regex can hide a mismatch (an <in-app-browser-context> opener "closed"
    by an </external_codex_apps_open_page> tag) or an unclosed nested block,
    and such residue must disqualify the turn instead of being stripped.
    A bare tag, mismatched types, nesting, or a duplicated close all fail
    closed, so callers can drop the whole turn.
    """
    stack: list[str] = []
    for match in HOST_CONTEXT_TAG.finditer(text or ""):
        tag = match.group(0)
        if tag.startswith("</"):
            kind = re.match(r"</([A-Za-z_]+)", tag)
            if not stack or stack[-1] != kind.group(1).lower():
                return True
            stack.pop()
        else:
            kind = re.match(r"<([A-Za-z_]+)", tag)
            if kind.group(1).lower() in stack:
                return True
            stack.append(kind.group(1).lower())
    return bool(stack)


def _raw_message_texts(message: Any) -> list[str]:
    texts: list[str] = []
    if isinstance(message, str):
        texts.append(message)
    elif isinstance(message, dict):
        block_type = str(message.get("type") or "")
        if block_type in {"tool_result", "tool_use", "function_call", "function_call_output"}:
            return []
        if isinstance(message.get("text"), str):
            texts.append(message["text"])
        else:
            texts.extend(_raw_message_texts(message.get("content")))
    elif isinstance(message, list):
        for item in message:
            if isinstance(item, str):
                texts.append(item)
            elif isinstance(item, dict):
                item_type = str(item.get("type") or "")
                if item_type in {"tool_result", "tool_use", "function_call", "function_call_output"}:
                    continue
                # Reasoning-only blocks carry no user-visible text; the extractor
                # drops them on purpose, so they are a known shape, not an
                # unknown payload.
                if item_type in {"thinking", "redacted_thinking"}:
                    continue
                if item_type in {"text", "input_text", "output_text"} and isinstance(item.get("text"), str):
                    texts.append(item["text"])
                elif not item_type and isinstance(item.get("content"), str):
                    texts.append(item["content"])
                elif not item_type and isinstance(item.get("text"), str):
                    texts.append(item["text"])
    return texts


def extract_message_text(message: Any) -> list[str]:
    cleaned: list[str] = []
    for text in _raw_message_texts(message):
        stripped = strip_framework_injection(text)
        if stripped.strip():
            cleaned.append(stripped)
    return cleaned


def extract_claude_text(record: dict[str, Any]) -> list[str]:
    record_type = record.get("type") or record.get("role")
    if record_type == "message":
        # WorkBuddy/CodeBuddy mark conversation rows as type=message and keep
        # the speaker in the top-level role.
        record_type = record.get("role")
    if record_type not in {"user", "assistant"}:
        return []
    message = record.get("message")
    return extract_message_text(message if message is not None else record.get("content"))


def claude_human_text(record: dict[str, Any]) -> list[str]:
    """Return only genuine outer-user text; tool_result blocks are never human."""
    record_type = record.get("type") or record.get("role")
    if record_type == "message":
        record_type = record.get("role")
    if record_type != "user":
        return []
    message = record.get("message")
    if isinstance(message, dict) and message.get("role") not in {None, "", "user"}:
        return []
    # Human-turn text remains raw: provenance gates in public_workflow must
    # see a malformed wrapper before stripping can hide the problem.
    return _raw_message_texts(message if message is not None else record.get("content"))


def extract_codex_text(record: dict[str, Any]) -> list[str]:
    payload = record.get("payload")
    if not isinstance(payload, dict):
        return []

    record_type = record.get("type")
    if record_type == "event_msg":
        message = payload.get("message")
        return [message] if isinstance(message, str) else []

    if record_type != "response_item":
        return []

    payload_type = payload.get("type")
    if payload_type == "message":
        if payload.get("role") in {"developer", "system"}:
            return []
        # User text remains raw for the same provenance reason as Claude.
        if payload.get("role") == "user":
            return _raw_message_texts(payload.get("content"))
        return extract_message_text(payload.get("content"))
    if payload_type == "function_call":
        name = payload.get("name") or ""
        args = payload.get("arguments") or ""
        return [compact_text(f"{name} {args}", 500)] if args else [str(name)]
    if payload_type == "function_call_output":
        output = payload.get("output") or ""
        if isinstance(output, str) and any(flag in output.lower() for flag in ["error", "failed", "traceback", "not found", "permission"]):
            return [compact_text(output, 500)]
    return []


def _normalized_event_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def record_text_events(record: dict[str, Any], source: str) -> list[tuple[str, str]]:
    """Return (semantic role, text) pairs and collapse mirrored Codex events later."""
    if source == "claude-code":
        record_type = record.get("type") or record.get("role")
        if record_type == "message":
            # WorkBuddy/CodeBuddy use type=message with the speaker in role.
            record_type = record.get("role")
        role = "human" if record_type == "user" else "assistant"
        texts = claude_human_text(record) if role == "human" else extract_claude_text(record)
        return [(role, item) for item in texts]

    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    if record.get("type") == "event_msg":
        payload_type = payload.get("type")
        role = "human" if payload_type == "user_message" else "assistant"
    elif record.get("type") == "response_item" and payload.get("type") == "message":
        role = "human" if payload.get("role") == "user" else "assistant"
    else:
        role = "tool"
    return [(role, item) for item in extract_codex_text(record)]


def _flatten_catalog_strings(value: Any, *, limit: int = 80) -> list[str]:
    output: list[str] = []
    if isinstance(value, str):
        text = " ".join(value.split()).strip()
        if 2 <= len(text) <= 240:
            output.append(text)
    elif isinstance(value, dict):
        for item in value.values():
            output.extend(_flatten_catalog_strings(item, limit=limit))
            if len(output) >= limit:
                break
    elif isinstance(value, list):
        for item in value:
            output.extend(_flatten_catalog_strings(item, limit=limit))
            if len(output) >= limit:
                break
    return output[:limit]


def collect_core_skill_data(
    inventory_path: Path | None = None,
    portraits_path: Path | None = None,
) -> tuple[list[str], list[dict[str, Any]], dict[str, Any]]:
    """Load the inventory candidate universe and overlay core metadata.

    ``core_skills.yaml`` is a priority/keyword overlay, never the complete
    candidate list. A missing or malformed runtime inventory is an explicit
    degraded mode returned to both the runtime source index and CLI result.
    """
    core_data = load_yaml(CORE_SKILLS_PATH)
    raw_core = core_data.get("core_skills", []) if isinstance(core_data.get("core_skills"), list) else []
    core_skills = [item for item in raw_core if isinstance(item, dict) and item.get("id")]
    core_by_id = {str(item["id"]): item for item in core_skills}
    inventory_path = inventory_path or (RUNTIME_ROOT / "skill-inventory.json")
    portraits_path = portraits_path or (RUNTIME_ROOT / "skill-portraits.json")
    inventory = read_json(inventory_path, None)
    inventory_skills = inventory.get("skills") if isinstance(inventory, dict) else None

    portraits_payload = read_json(portraits_path, {})
    portraits = portraits_payload.get("portraits", {}) if isinstance(portraits_payload, dict) else {}
    if isinstance(portraits, list):
        portraits = {
            str(item.get("skill_key")): item
            for item in portraits
            if isinstance(item, dict) and item.get("skill_key")
        }
    if not isinstance(portraits, dict):
        portraits = {}

    degraded = not isinstance(inventory_skills, list) or not inventory_skills
    if degraded:
        candidates = [dict(item) for item in core_skills]
        status_name = "core_fallback"
        inventory_count = 0
    else:
        candidates = []
        for raw in inventory_skills:
            if not isinstance(raw, dict):
                continue
            skill_id = str(raw.get("id") or raw.get("name") or "").strip()
            if not skill_id:
                continue
            core = core_by_id.get(skill_id, {})
            skill_key = str(raw.get("skill_key") or skill_id)
            portrait = raw.get("portrait") if isinstance(raw.get("portrait"), dict) else portraits.get(skill_key, {})
            display_name = str(
                raw.get("name") or raw.get("title") or core.get("display_name") or skill_id
            ).strip()
            description = str(raw.get("description") or "").strip()
            search_terms = []
            for value in [skill_id, display_name, description, *_flatten_catalog_strings(portrait)]:
                normalized = " ".join(str(value).split()).strip()
                if normalized and normalized not in search_terms:
                    search_terms.append(normalized)
            candidates.append(
                {
                    **raw,
                    "id": skill_id,
                    "display_name": display_name,
                    "description": description,
                    "portrait": portrait if isinstance(portrait, dict) else {},
                    "domain_keywords": list(core.get("domain_keywords", []) or []),
                    "priority": core.get("priority", "normal"),
                    "is_core": bool(core),
                    "search_terms": search_terms[:80],
                }
            )
        status_name = "inventory_complete"
        inventory_count = len(candidates)

    keywords: list[str] = []
    for skill in candidates:
        for keyword in [
            *(skill.get("domain_keywords", []) or []),
            *(skill.get("search_terms", []) or []),
        ]:
            if isinstance(keyword, str) and 2 <= len(keyword) <= 80 and keyword not in keywords:
                keywords.append(keyword)
    status = {
        "status": status_name,
        "candidate_scope": "inventory" if not degraded else "core_only_degraded",
        "inventory_available": not degraded,
        "inventory_skill_count": inventory_count,
        "core_skill_count": len(core_skills),
        "candidate_skill_count": len(candidates),
        "inventory_ref": "runtime/skill-inventory.json",
    }
    return keywords, candidates, status


def phrase_hits(text: str, phrases: Iterable[str]) -> list[str]:
    lower = text.lower()
    hits = []
    for phrase in phrases:
        if not phrase:
            continue
        if phrase.lower() in lower:
            hits.append(phrase)
    return hits


def match_related_skills(text: str, skills: list[dict[str, Any]]) -> list[str]:
    related: list[tuple[float, int, str]] = []
    lower = text.lower()
    for skill in skills:
        skill_id = str(skill.get("id", ""))
        display_name = str(skill.get("display_name") or skill.get("name") or skill.get("title") or "")
        keywords = [
            str(item)
            for item in [
                *(skill.get("domain_keywords", []) or []),
                *(skill.get("search_terms", []) or []),
            ]
        ]
        score = 0.0
        exact_match = False
        if skill_id and skill_id.lower() in lower:
            score += 3
            exact_match = True
        if display_name and display_name.lower() in lower:
            score += 2
            exact_match = True
        keyword_hits = [kw for kw in keywords if kw and kw.lower() in lower and kw not in GENERIC_SKILL_KEYWORDS]
        score += min(len(keyword_hits), 4)
        if skill_id == "self-evolve" and not exact_match and score < 3:
            continue
        if score >= 4 or exact_match:
            priority_rank = {"high": 2, "medium": 1}.get(str(skill.get("priority", "")).lower(), 0)
            related.append((score, priority_rank, skill_id))
    related.sort(key=lambda item: (-item[0], -item[1], item[2]))
    return [skill_id for _, _, skill_id in related[:8]]


def choose_work_stage(text: str) -> str:
    stages = [
        ("article_draft", ["文章", "初稿", "公众号", "标题", "发布", "复盘"]),
        ("verification", ["验证", "测试通过", "截图", "Playwright", "py_compile", "lint", "build"]),
        ("skill_patch", ["修改 skill", "更新 skill", "SKILL.md", "references", "CHANGELOG", "TASKS", "DECISIONS"]),
        ("workflow_design", ["工作流", "流程", "架构", "设计", "方案", "规划", "检查清单"]),
        ("tool_test", ["测试", "工具", "M3", "OCR", "抽帧", "录屏", "模型"]),
        ("research", ["研究", "检索", "调研", "分析", "比较"]),
    ]
    for stage, phrases in stages:
        if phrase_hits(text, phrases):
            return stage
    return "unknown"


def choose_collaboration_mode(path: Path, text: str) -> str:
    if "subagents" in path.parts or "subagent" in text.lower() or "multi-agent" in text.lower():
        return "multi_agent"
    if phrase_hits(text, ["SE_EXTRACTION", "headless", "SELF_EVOLVE_HEADLESS"]):
        return "headless"
    if phrase_hits(text, ["SessionEnd", "hook", "hooks"]):
        return "hook"
    if phrase_hits(text, ["人工审", "人在回路", "review", "候选"]):
        return "human_review_loop"
    return "single_agent"


def classify_session(
    path: Path,
    text: str,
    related_skills: list[str],
    matched_keywords: list[str],
) -> tuple[str, str, list[str]]:
    if phrase_hits(text, MACHINE_MARKERS):
        return "machine_generated", "skip", ["检测到 Self Evolve/headless 机器会话标记"]

    meta_hits = phrase_hits(text, META_DESIGN_PHRASES)
    article_hits = phrase_hits(text, ARTICLE_PHRASES)
    substantive_hits = phrase_hits(text, SUBSTANTIVE_PHRASES)
    tooling_hits = phrase_hits(text, TOOLING_PHRASES)
    git_hits = phrase_hits(text, GIT_PHRASES)
    maintenance_hits = phrase_hits(text, MAINTENANCE_PHRASES)
    software_hits = phrase_hits(text, SOFTWARE_UPDATE_PHRASES)
    method_hits = phrase_hits(text, METHOD_SIGNAL_PHRASES)
    intent_hits = phrase_hits(text, USER_INTENT_PHRASES)

    reasons = []
    if meta_hits:
        reasons.append(f"元设计信号：{', '.join(meta_hits[:5])}")
    if article_hits:
        reasons.append(f"文章信号：{', '.join(article_hits[:5])}")
    if tooling_hits:
        reasons.append(f"工具链信号：{', '.join(tooling_hits[:5])}")
    if git_hits and not (meta_hits or substantive_hits or method_hits or intent_hits):
        reasons.append("普通 git 操作信号，默认只建薄索引")
    if maintenance_hits and not (meta_hits or substantive_hits or method_hits or intent_hits):
        reasons.append("维护/环境操作信号，默认只建薄索引")
    if software_hits and not (meta_hits or substantive_hits or method_hits or intent_hits):
        reasons.append("软件更新信号，默认只建薄索引")

    if len(meta_hits) >= 2 or "self-evolve" in related_skills:
        session_class = "meta_design"
    elif len(article_hits) >= 2 and (substantive_hits or method_hits or intent_hits):
        session_class = "article_signal"
    elif related_skills or len(matched_keywords) >= 2 or len(substantive_hits) >= 2 or method_hits or intent_hits:
        session_class = "substantive"
    elif len(tooling_hits) >= 2:
        session_class = "tooling_fix"
    elif len(software_hits) >= 1:
        session_class = "software_update"
    elif len(git_hits) >= 2:
        session_class = "git_ops"
    elif len(maintenance_hits) >= 1:
        session_class = "maintenance"
    elif article_hits:
        session_class = "article_signal"
    else:
        session_class = "maintenance"
        reasons.append("未出现稳定方法论或核心 Skill 信号，暂按薄索引处理")

    return session_class, SESSION_CLASS_POLICY[session_class], reasons


def top_keywords(text: str, core_keywords: list[str], related_skills: list[str], cwd: str) -> list[str]:
    candidates: list[str] = []
    for keyword in core_keywords:
        if keyword in GENERIC_TOPIC_TERMS:
            continue
        if keyword in text and keyword not in candidates:
            candidates.append(keyword)
    for phrase_group in (
        META_DESIGN_PHRASES,
        ARTICLE_PHRASES,
        METHOD_SIGNAL_PHRASES,
        SUBSTANTIVE_PHRASES,
        TOOLING_PHRASES,
    ):
        for phrase in phrase_group:
            if phrase in GENERIC_TOPIC_TERMS:
                continue
            if phrase.lower() in text.lower() and phrase not in candidates:
                candidates.append(phrase)
    for skill_id in related_skills:
        if skill_id not in candidates:
            candidates.append(skill_id)
    cwd_name = Path(cwd).name if cwd else ""
    if cwd_name and len(cwd_name) > 2 and cwd_name not in candidates and cwd_name.lower() not in {item.lower() for item in GENERIC_TOPIC_TERMS}:
        candidates.append(cwd_name)
    return candidates[:14]


def detect_signals(texts: list[str], phrases: list[str], limit: int = 5) -> list[str]:
    combined = "\n".join(texts)
    return phrase_hits(combined, phrases)[:limit]


def extract_questions(texts: list[str], limit: int = 3) -> list[str]:
    questions = []
    for text in texts:
        if is_report_noise(text):
            continue
        for part in re.split(r"[。！？\n]", text):
            if is_report_noise(part):
                continue
            if any(marker in part for marker in ["是不是", "能不能", "是否", "怎么", "如何", "？", "?"]):
                item = compact_text(part, 120)
                if item and item not in questions:
                    questions.append(item)
            if len(questions) >= limit:
                return questions
    return questions


def extract_decisions(texts: list[str], limit: int = 4) -> list[str]:
    """句子级决策信号抽取（区别于 extract_questions 的疑问 cue）。

    ``decisions`` 原为 3 条硬编码分类模板，全语料只有 3 个唯一值；现按决策 cue 词
    切句抽取，让字段承载真实决策内容。
    """
    decisions: list[str] = []
    cues = ("决定", "改为", "改回", "因此", "选定", "采用", "放弃", "敲定", "最终", "不再", "统一用")
    # 排除对话碎片：句首口语词 + 短（"我读这些给最终结论"）/ 模糊对话词（"你确定能查看吗"）
    # "确定" 不作 cue：会误匹配"精确"等子串
    conversational = re.compile(r"^(我|咱们|我们|这次|那|查|读|看|想|行|好|可以|对|啊|哎|嗯|噢|哦)")
    vague = re.compile(r"(在哪|能够|读这些|查透|觉得|似乎|也许|你确定|你觉得|是不是|能不能)")
    for text in texts:
        if is_report_noise(text):
            continue
        for part in re.split(r"[。！？\n]", text):
            stripped = part.strip()
            if is_report_noise(stripped) or len(stripped) < 12:
                continue
            if conversational.match(stripped) and len(stripped) < 18:
                continue
            if vague.search(stripped):
                continue
            if any(cue in stripped for cue in cues) or re.search(r"采用.{0,12}而非", stripped):
                item = compact_text(stripped, 120)
                if item and item not in decisions:
                    decisions.append(item)
            if len(decisions) >= limit:
                return decisions
    return decisions


def evidence_snippets(texts: list[str], limit: int = 8) -> list[str]:
    signals = USER_INTENT_PHRASES + METHOD_SIGNAL_PHRASES + ARTICLE_PHRASES + TOOLING_PHRASES
    hits: list[str] = []
    seen: set[str] = set()
    for text in texts:
        if is_report_noise(text):
            continue
        if not any(signal.lower() in text.lower() for signal in signals):
            continue
        snippet = compact_text(text, 220)
        if snippet and snippet not in seen:
            seen.add(snippet)
            hits.append(snippet)
    # 等间距抽样：从命中里均匀取 limit 个，覆盖头/中/尾（避免长 session 只抓早期）
    if len(hits) <= limit:
        snippets = hits
    else:
        step = len(hits) / limit
        snippets = []
        picked: set[int] = set()
        for i in range(limit):
            idx = int(i * step)
            if idx not in picked:
                picked.add(idx)
                snippets.append(hits[idx])
    # fallback：无 signal 命中时取前 limit 个任意
    if not snippets:
        for text in texts:
            if is_report_noise(text):
                continue
            snippet = compact_text(text, 160)
            if snippet:
                snippets.append(snippet)
            if len(snippets) >= limit:
                break
    return snippets[:limit]


def first_user_title(texts: list[str], cwd: str, related_skills: list[str]) -> str:
    for text in texts:
        clean = compact_text(text, 90)
        if len(clean) >= 8:
            return clean
    if related_skills:
        return f"{related_skills[0]} 相关工作"
    if cwd:
        return f"{Path(cwd).name} 相关会话"
    return "未命名会话"


def summarize_records(
    path: Path,
    source: str,
    records: list[dict[str, Any]],
    core_keywords: list[str],
    skills: list[dict[str, Any]],
    *,
    source_variant: str = "",
    read_stats: JsonlReadStats | None = None,
) -> SessionSummary | None:
    texts: list[str] = []
    user_texts: list[str] = []
    timestamps: list[datetime] = []
    cwd = ""
    session_id = path.stem
    agent_context: dict[str, Any] = {}
    previous_event: tuple[str, str] | None = None
    duplicate_text_events = 0
    human_event_count = 0

    for record in records:
        dt = parse_time(record.get("timestamp"))
        if dt:
            timestamps.append(dt)

        if source == "claude-code":
            if record.get("sessionId"):
                session_id = str(record.get("sessionId"))
            cwd = cwd or str(record.get("cwd") or "")
            if record.get("gitBranch"):
                agent_context["git_branch"] = record.get("gitBranch")
        else:
            payload = record.get("payload")
            if isinstance(payload, dict):
                payload_dt = parse_time(payload.get("timestamp") or payload.get("started_at"))
                if payload_dt:
                    timestamps.append(payload_dt)
                if record.get("type") == "session_meta":
                    session_id = str(payload.get("id") or session_id)
                    cwd = cwd or str(payload.get("cwd") or "")
                    agent_context.update(
                        {
                            "model_provider": payload.get("model_provider", "unknown"),
                            "thread_source": payload.get("thread_source", "unknown"),
                            "source": payload.get("source", "unknown"),
                            "originator": payload.get("originator", "unknown"),
                        }
                    )
                    git = payload.get("git")
                    if isinstance(git, dict) and git.get("branch"):
                        agent_context["git_branch"] = git.get("branch")
                elif record.get("type") == "turn_context":
                    cwd = cwd or str(payload.get("cwd") or "")
                    if payload.get("model"):
                        agent_context["model"] = payload.get("model")

        for role, extracted in record_text_events(record, source):
            # User events stay raw for provenance callers, but summaries and
            # evidence snippets must never expose host wrapper boilerplate.
            extracted = strip_framework_injection(extracted)
            normalized = _normalized_event_text(extracted)
            if not normalized:
                continue
            # Codex mirrors a user message in adjacent event_msg/response_item
            # records. Only collapse the adjacent mirror: the same feedback may
            # legitimately recur later in a session and remains distinct evidence.
            event_key = (role, normalized)
            if event_key == previous_event:
                duplicate_text_events += 1
                continue
            previous_event = event_key
            texts.append(extracted)
            if role == "human":
                user_texts.append(extracted)
                human_event_count += 1

    texts = [text for text in texts if isinstance(text, str) and text.strip()]
    # 空 texts 宽容：metadata-only file / workflow journal / 老 schema / transcripts 都产 placeholder summary
    # 不再 return None；由 line 1389 后 placeholder override 设 summary_policy=index_only

    useful_texts = [text for text in texts if not is_context_noise(text)]
    useful_user_texts = [text for text in user_texts if not is_context_noise(text)]
    if not useful_texts:
        useful_texts = texts[:3]

    def bounded_join(items: list[str], limit: int = 50000) -> str:
        joined = "\n".join(items)
        if len(joined) <= limit:
            return joined
        half = limit // 2
        return f"{joined[:half]}\n<中段已压缩>\n{joined[-half:]}"

    combined = bounded_join(texts)
    useful_combined = bounded_join(useful_texts)
    signal_text = useful_combined or combined
    matched_keywords = [keyword for keyword in core_keywords if keyword in signal_text]
    related_skills = match_related_skills(signal_text, skills)
    session_class, summary_policy, noise_reasons = classify_session(path, signal_text, related_skills, matched_keywords)
    sensitive_markers = detect_sensitive_markers(bounded_join(useful_user_texts) or useful_combined)
    if timestamps:
        started = min(timestamps)
    else:
        try:
            started = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        except OSError:
            started = datetime.now(timezone.utc)
    ended = max(timestamps) if timestamps else started

    report_source_texts = useful_user_texts or useful_texts or texts
    report_texts = [text for text in report_source_texts if not is_report_noise(text)]
    if not report_texts:
        report_texts = [text for text in useful_texts if not is_report_noise(text)]
    title = first_user_title(report_texts, cwd, related_skills)
    if sensitive_markers and any(marker in (bounded_join(useful_user_texts) or useful_combined) for marker in ["人民法院", "送达文书", "案号", "被告", "原告"]):
        title = "案件材料或法院通知处理（已脱敏）"
    topic_keywords = top_keywords(signal_text, core_keywords, related_skills, cwd)
    work_stage = choose_work_stage(signal_text)
    collaboration_mode = choose_collaboration_mode(path, signal_text)
    fingerprint = transcript_fingerprint(path)

    decisions = extract_decisions(useful_texts)
    if not decisions:
        # fallback：无显式决策句时保留分类标签（非句子级抽取，避免字段空）
        if detect_signals(useful_texts, USER_INTENT_PHRASES):
            decisions.append("用户表达了沉淀、升级、写作或后续复用意图")
        if detect_signals(useful_texts, METHOD_SIGNAL_PHRASES):
            decisions.append("会话包含可复用流程、标准或验收边界")
        if session_class == "tooling_fix":
            decisions.append("会话体现工具链故障或路径/配置问题，需观察是否重复出现")

    redaction_notes = []
    if sensitive_markers:
        redaction_notes.append("检测到可能敏感信息，报告输出已使用短摘要和脱敏片段")
    agent_context["human_event_count"] = human_event_count
    agent_context["deduplicated_text_events"] = duplicate_text_events

    if not texts:
        # 空 texts placeholder：metadata-only / 老 schema / workflow journal 等
        # summary_policy=index_only 不进聚类；保留原文备份/索引可检索
        title = title or f"{source_variant or source} 元数据会话"
        summary_policy = "index_only"
        session_class = "maintenance"
        noise_reasons = list(noise_reasons) + ["empty_texts_metadata_only"]
        topic_keywords = []

    return SessionSummary(
        source=source,
        source_variant=source_variant or source,
        session_id=session_id,
        transcript_path=str(path),
        started_at=format_dt(started),
        ended_at=format_dt(ended),
        cwd=cwd,
        cwd_label=compact_path(cwd),
        agent_context=agent_context,
        topic_title=title,
        topic_keywords=topic_keywords,
        session_class=session_class,
        summary_policy=summary_policy,
        noise_reasons=noise_reasons,
        related_skills=related_skills,
        work_stage=work_stage,
        agent_collaboration_mode=collaboration_mode,
        decisions=decisions,
        open_questions=extract_questions(report_texts),
        upgrade_signals=detect_signals(useful_texts, METHOD_SIGNAL_PHRASES + USER_INTENT_PHRASES),
        article_signals=detect_signals(useful_user_texts, ARTICLE_PHRASES),
        timeline_signals=detect_signals(useful_texts, META_DESIGN_PHRASES + SUBSTANTIVE_PHRASES + TOOLING_PHRASES),
        sensitive_risk=bool(sensitive_markers),
        redaction_notes=redaction_notes,
        evidence_snippets=evidence_snippets(report_texts),
        transcript_mtime=float(fingerprint["transcript_mtime"] or 0),
        transcript_size=int(fingerprint["transcript_size"] or 0),
        transcript_fingerprint=str(fingerprint.get("transcript_fingerprint") or ""),
        total_line_count=(read_stats.total_lines if read_stats else len(records)),
        parsed_line_count=(read_stats.parsed_lines if read_stats else len(records)),
        invalid_line_count=(read_stats.invalid_lines if read_stats else 0),
        selected_line_count=(read_stats.selected_lines if read_stats else len(records)),
        skipped_line_count=(
            max(0, read_stats.total_lines - read_stats.selected_lines) if read_stats else 0
        ),
        selected_record_count=(read_stats.selected_lines if read_stats else len(records)),
        skipped_oversized_tool_lines=(read_stats.skipped_oversized_tool_lines if read_stats else 0),
        skipped_oversized_lines=(read_stats.skipped_oversized_lines if read_stats else 0),
    )


def discover_claude_paths(cutoff: datetime | None, include_subagents: bool) -> list[Path]:
    # transcripts 总量小、无项目子树，豁免 recent cutoff 全量扫（否则老 mtime 永久漏采）；
    # projects 仍按 cutoff 增量。
    roots = [
        (Path.home() / ".claude" / "projects", cutoff),
        (Path.home() / ".claude" / "transcripts", None),
    ]
    paths: list[Path] = []
    for root, root_cutoff in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.jsonl"):
            if not include_subagents and "subagents" in path.parts:
                continue
            try:
                if root_cutoff and datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc) < root_cutoff:
                    continue
            except OSError:
                continue
            paths.append(path)
    return sorted(paths, key=lambda item: item.stat().st_mtime, reverse=True)


def discover_codex_paths(cutoff: datetime | None) -> list[Path]:
    paths: list[Path] = []
    for root in (Path.home() / ".codex" / "sessions", Path.home() / ".codex" / "archived_sessions", Path.home() / ".codex" / "_quarantine"):
        if not root.exists():
            continue
        for path in root.rglob("*.jsonl"):
            try:
                if cutoff and datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc) < cutoff:
                    continue
            except OSError:
                continue
            paths.append(path)
    return sorted(paths, key=lambda item: item.stat().st_mtime, reverse=True)


def should_keep_by_time(summary: SessionSummary, cutoff: datetime | None) -> bool:
    if cutoff is None:
        return True
    dt = parse_time(summary.ended_at) or parse_time(summary.started_at)
    if dt is None:
        return True
    return dt.astimezone(timezone.utc) >= cutoff


def summary_json_paths() -> Iterable[Path]:
    if not SESSION_SUMMARY_DIR.exists():
        return []
    return SESSION_SUMMARY_DIR.rglob("*.json")


def build_existing_summary_index() -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for path in summary_json_paths():
        data = read_json(path, {})
        if not isinstance(data, dict):
            continue
        transcript_path = str(data.get("transcript_path") or "")
        if not transcript_path:
            continue
        try:
            summary_mtime = path.stat().st_mtime
        except OSError:
            continue
        previous = index.get(transcript_path)
        if previous is None or summary_mtime >= previous["summary_mtime"]:
            index[transcript_path] = {
                "path": str(path),
                "summary_mtime": summary_mtime,
                "data": data,
            }
    return index


def existing_summary_status(existing: dict[str, Any] | None, path: Path, refresh_existing: bool) -> str:
    if existing is None:
        return "missing"

    data = existing.get("data") if isinstance(existing, dict) else {}
    if not isinstance(data, dict):
        return "stale"

    fingerprint = transcript_fingerprint(path)
    existing_fingerprint = str(data.get("transcript_fingerprint") or "")
    if existing_fingerprint.startswith("sha256:"):
        return "current" if existing_fingerprint == fingerprint["transcript_fingerprint"] else "stale"

    # v0.6 and earlier only stored mtime/size (or a hash of that metadata).
    # Never treat that weak identity as current: refresh it into a content hash.
    if existing_fingerprint or data.get("transcript_mtime") not in (None, "", 0):
        return "stale_legacy"

    if refresh_existing:
        return "stale_legacy"
    return "legacy"


def summary_from_dict(data: dict[str, Any]) -> SessionSummary | None:
    allowed = set(SessionSummary.__dataclass_fields__)
    payload = {key: value for key, value in data.items() if key in allowed}
    payload.setdefault("source_variant", str(payload.get("source") or "unknown"))
    try:
        return SessionSummary(**payload)
    except (TypeError, ValueError):
        return None


def dedupe_session_summaries(summaries: Iterable[SessionSummary]) -> tuple[list[SessionSummary], int]:
    """Prefer the active/richer representation of the same stable session id."""
    priorities = {
        "codex_active": 4,
        "codex_archived": 3,
        "claude_project": 2,
        "claude_transcript": 1,
        "codex_quarantine": 1,
        "claude_subagent": 0,
    }
    chosen: dict[tuple[str, str], SessionSummary] = {}
    duplicate_count = 0
    for summary in summaries:
        key = (summary.source, summary.session_id)
        previous = chosen.get(key)
        if previous is None:
            chosen[key] = summary
            continue
        duplicate_count += 1
        previous_rank = (
            priorities.get(previous.source_variant, 0),
            previous.selected_record_count,
            previous.transcript_size,
            previous.ended_at,
        )
        candidate_rank = (
            priorities.get(summary.source_variant, 0),
            summary.selected_record_count,
            summary.transcript_size,
            summary.ended_at,
        )
        if candidate_rank > previous_rank:
            chosen[key] = summary
    output = sorted(chosen.values(), key=lambda item: (item.started_at or "", item.source, item.session_id))
    return output, duplicate_count


def source_variant_for_path(source: str, path: Path) -> str:
    parts = set(path.parts)
    if source == "claude-code":
        if "subagents" in parts:
            return "claude_subagent"
        return "claude_transcript" if "transcripts" in parts else "claude_project"
    if "_quarantine" in parts:
        return "codex_quarantine"
    return "codex_archived" if "archived_sessions" in parts else "codex_active"


def discover_source_transcripts(
    sources: set[str], cutoff: datetime | None, include_subagents: bool
) -> list[SourceTranscript]:
    discovered: list[SourceTranscript] = []
    if "claude" in sources or "claude-code" in sources:
        discovered.extend(
            SourceTranscript("claude-code", source_variant_for_path("claude-code", path), path)
            for path in discover_claude_paths(cutoff, include_subagents)
        )
    if "codex" in sources:
        discovered.extend(
            SourceTranscript("codex", source_variant_for_path("codex", path), path)
            for path in discover_codex_paths(cutoff)
        )
    return discovered


def discover_source_paths(
    sources: set[str], cutoff: datetime | None, include_subagents: bool
) -> list[tuple[str, list[Path]]]:
    """Compatibility view grouped by stable source name."""
    grouped: defaultdict[str, list[Path]] = defaultdict(list)
    for item in discover_source_transcripts(sources, cutoff, include_subagents):
        grouped[item.source].append(item.path)
    return list(grouped.items())


def select_with_source_quota(
    candidates: list[tuple[float, SourceTranscript]], max_sessions: int
) -> tuple[list[tuple[float, SourceTranscript]], list[tuple[float, SourceTranscript]]]:
    """Cap globally while reserving a small deterministic quota per source."""
    ordered = sorted(candidates, key=lambda item: (-item[0], item[1].source, str(item[1].path)))
    if max_sessions <= 0:
        return [], ordered
    if len(ordered) <= max_sessions:
        return ordered, []
    source_names = sorted({item.source for _, item in ordered})
    minimum = max(1, min(10, max_sessions // max(1, len(source_names) * 3)))
    selected: list[tuple[float, SourceTranscript]] = []
    selected_paths: set[Path] = set()
    for source in source_names:
        if len(selected) >= max_sessions:
            break
        for candidate in (item for item in ordered if item[1].source == source):
            if len(selected) >= max_sessions:
                break
            if len([1 for _, chosen in selected if chosen.source == source]) >= minimum:
                break
            selected.append(candidate)
            selected_paths.add(candidate[1].path)
    for candidate in ordered:
        if len(selected) >= max_sessions:
            break
        if candidate[1].path not in selected_paths:
            selected.append(candidate)
            selected_paths.add(candidate[1].path)
    limited = [item for item in ordered if item[1].path not in selected_paths]
    return sorted(selected, key=lambda item: (-item[0], str(item[1].path))), limited


def update_backfill_state(stats: dict[str, Any], run_id: str, reset: bool) -> dict[str, Any]:
    previous = {} if reset else read_json(BACKFILL_STATE_PATH, {})
    if not isinstance(previous, dict):
        previous = {}
    cumulative = previous.get("cumulative", {}) if isinstance(previous.get("cumulative"), dict) else {}
    for key in ("runs", "indexed", "skipped_existing", "skipped_legacy", "stale_reindexed", "skipped_errors", "considered"):
        cumulative[key] = int(cumulative.get(key) or 0) + int(stats.get(key) or 0)
    cumulative["runs"] = int(cumulative.get("runs") or 0) + 1

    previous_failed = set(previous.get("failed_paths") or []) if isinstance(previous.get("failed_paths"), list) else set()
    failed_paths = sorted(previous_failed | {str(p) for p in (stats.get("failed_paths") or [])})
    state = {
        "schema_version": "1.0",
        "updated_at": format_dt(datetime.now(timezone.utc)),
        "run_id": run_id,
        "index_mode": "backfill",
        "completed": bool(stats.get("completed")),
        "failed_paths": failed_paths,
        "last_processed_path": stats.get("last_processed_path", ""),
        "last_processed_mtime": stats.get("last_processed_mtime", 0),
        "last_considered_path": stats.get("last_considered_path", ""),
        "last_considered_mtime": stats.get("last_considered_mtime", 0),
        "last_run": stats,
        "cumulative": cumulative,
    }
    write_json(BACKFILL_STATE_PATH, state)
    return state


def compute_coverage_metrics(sources: set[str], include_subagents: bool, existing_index: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """覆盖率对账：全量 discover（cutoff=None）vs 已索引。

    写入 ``source_index["coverage"]``：raw_total（全量发现）、unindexed_total（未索引数）、
    coverage_ratio（已索引百分比）。让面板/调度能直接读到"还差多少"，
    无需再跑一遍 discover+existing_index。
    """
    discovered = discover_source_transcripts(sources, None, include_subagents)
    raw_total = len(discovered)
    unindexed = sum(1 for item in discovered if str(item.path) not in existing_index)
    return {
        "raw_total": raw_total,
        "unindexed_total": unindexed,
        "coverage_ratio": round((raw_total - unindexed) * 100 / max(raw_total, 1), 2),
    }


def build_summaries(args: argparse.Namespace, core_keywords: list[str], skills: list[dict[str, Any]]) -> tuple[list[SessionSummary], dict[str, Any]]:
    window = parse_since(args.since)
    cutoff = datetime.now(timezone.utc) - window if window is not None else None
    sources = {item.strip() for item in args.sources.split(",") if item.strip()}
    source_index: dict[str, Any] = {
        "generated_at": format_dt(datetime.now(timezone.utc)),
        "since": args.since,
        "index_mode": args.index_mode,
        "sources": {},
    }
    summaries: list[SessionSummary] = []

    discovered = discover_source_transcripts(sources, cutoff, args.include_subagents)
    counts = Counter(item.source for item in discovered)
    for source, count in counts.items():
        source_index["sources"][source] = {
            "discovered": count,
            "limited": 0,
            "indexed": 0,
            "reused_unchanged": 0,
            "duplicates": 0,
            "skipped": 0,
        }

    candidates: list[tuple[float, SourceTranscript]] = []
    for item in discovered:
        try:
            modified_at = item.path.stat().st_mtime
        except OSError:
            source_index["sources"][item.source]["skipped"] += 1
            continue
        candidates.append((modified_at, item))
    candidates, limited = select_with_source_quota(candidates, args.max_sessions)
    for _, item in limited:
        source_index["sources"][item.source]["limited"] += 1

    existing_index = build_existing_summary_index()
    for _, item in candidates:
        path = item.path
        source = item.source
        existing = existing_index.get(str(path))
        if existing_summary_status(existing, path, False) == "current":
            cached = summary_from_dict(existing.get("data", {})) if existing else None
            if cached is not None:
                cached.source_variant = item.source_variant
                summaries.append(cached)
                source_index["sources"][source]["reused_unchanged"] += 1
                continue
        try:
            records, read_stats = read_jsonl_with_stats(path, max_lines=args.max_lines_per_session)
        except OSError as exc:
            # A-F3-R3：共享读取器现在传播打开失败；单对象失败可见、其余继续。
            print(f"读取失败跳过 {path}: {type(exc).__name__}", file=sys.stderr)
            source_index["sources"][source]["skipped"] += 1
            continue
        summary = summarize_records(
            path,
            source,
            records,
            core_keywords,
            skills,
            source_variant=item.source_variant,
            read_stats=read_stats,
        )
        if summary is None:
            source_index["sources"][source]["skipped"] += 1
            continue
        if not should_keep_by_time(summary, cutoff):
            source_index["sources"][source]["skipped"] += 1
            continue
        summaries.append(summary)
        source_index["sources"][source]["indexed"] += 1

    summaries, duplicate_count = dedupe_session_summaries(summaries)
    source_index["deduplicated_sessions"] = duplicate_count
    # The count is global because duplicates can originate in active/archive or
    # projects/transcripts adapters. Keep per-source diagnostics as well.
    for source in source_index["sources"]:
        source_index["sources"][source]["duplicates"] = duplicate_count if len(source_index["sources"]) == 1 else 0
    source_index["coverage"] = compute_coverage_metrics(sources, args.include_subagents, existing_index)
    return summaries, source_index


def build_backfill_summaries(args: argparse.Namespace, core_keywords: list[str], skills: list[dict[str, Any]], run_id: str) -> tuple[list[SessionSummary], dict[str, Any]]:
    sources = {item.strip() for item in args.sources.split(",") if item.strip()}
    source_index: dict[str, Any] = {
        "generated_at": format_dt(datetime.now(timezone.utc)),
        "since": "all",
        "index_mode": "backfill",
        "sources": {},
    }
    summaries: list[SessionSummary] = []
    existing_index = build_existing_summary_index()
    previous_state = read_json(BACKFILL_STATE_PATH, {}) if not args.reset_backfill else {}
    known_failed = set()
    if isinstance(previous_state, dict) and isinstance(previous_state.get("failed_paths"), list):
        known_failed = {str(p) for p in previous_state["failed_paths"]}
    discovered = discover_source_transcripts(sources, None, args.include_subagents)

    candidates: list[tuple[float, SourceTranscript]] = []
    counts = Counter(item.source for item in discovered)
    for source, count in counts.items():
        source_index["sources"][source] = {
            "discovered": count,
            "indexed": 0,
            "skipped": 0,
            "skipped_existing": 0,
            "skipped_legacy": 0,
            "stale_reindexed": 0,
        }
    skipped_failed = 0
    for item in discovered:
        if str(item.path) in known_failed:
            skipped_failed += 1
            continue
        try:
            modified_at = item.path.stat().st_mtime
        except OSError:
            source_index["sources"][item.source]["skipped"] += 1
            continue
        candidates.append((modified_at, item))

    reverse = args.backfill_order != "oldest-first"
    candidates.sort(key=lambda item: item[0], reverse=reverse)

    # 方案 B：cursor lower-bound 过滤（让 backfill 真正 cursor-driven，不重复吃头部 dedupe）
    if not args.reset_backfill and isinstance(previous_state, dict):
        lpm = previous_state.get("last_processed_mtime")
        if isinstance(lpm, (int, float)) and lpm > 0:
            cursor_mtime = float(lpm)
            if reverse:  # newest-first: 跳过 mtime >= cursor（已 processed）
                candidates = [(t, item) for t, item in candidates if t < cursor_mtime]
            else:  # oldest-first: 跳过 mtime <= cursor（已 processed）
                candidates = [(t, item) for t, item in candidates if t > cursor_mtime]

    batch_size = max(1, int(args.backfill_batch_size or 200))
    stats: dict[str, Any] = {
        "started_at": format_dt(datetime.now(timezone.utc)),
        "batch_size": batch_size,
        "order": args.backfill_order,
        "total_discovered": len(candidates),
        "existing_summary_count": len(existing_index),
        "considered": 0,
        "indexed": 0,
        "skipped_existing": 0,
        "skipped_legacy": 0,
        "stale_reindexed": 0,
        "skipped_errors": 0,
        "retry_pending": 0,
        "failed_paths": [],
        "skipped_failed": skipped_failed,
        "completed": False,
        "reset": bool(args.reset_backfill),
        "refresh_existing": bool(args.backfill_refresh_existing),
        "state_path": str(BACKFILL_STATE_PATH),
    }

    for modified_at, item in candidates:
        source = item.source
        path = item.path
        if stats["indexed"] >= batch_size:
            break
        stats["considered"] += 1
        stats["last_considered_path"] = str(path)
        stats["last_considered_mtime"] = modified_at

        status = existing_summary_status(existing_index.get(str(path)), path, args.backfill_refresh_existing)
        if status == "current":
            source_index["sources"][source]["skipped_existing"] += 1
            stats["skipped_existing"] += 1
            continue
        if status == "legacy":
            source_index["sources"][source]["skipped_legacy"] += 1
            stats["skipped_legacy"] += 1
            continue
        if status in {"stale", "stale_legacy"}:
            source_index["sources"][source]["stale_reindexed"] += 1
            stats["stale_reindexed"] += 1

        try:
            records, read_stats = read_jsonl_with_stats(path, max_lines=args.max_lines_per_session)
        except OSError as exc:
            # A-F3-R3：backfill 单对象读取失败可见、计入错误、其余继续。
            print(f"读取失败跳过 {path}: {type(exc).__name__}", file=sys.stderr)
            stats["skipped_errors"] += 1
            stats["failed_paths"].append(str(path))
            continue
        summary = summarize_records(
            path,
            source,
            records,
            core_keywords,
            skills,
            source_variant=item.source_variant,
            read_stats=read_stats,
        )
        if summary is None:
            source_index["sources"][source]["skipped"] += 1
            stats["skipped_errors"] += 1
            stats["retry_pending"] += 1
            stats["failed_paths"].append(str(path))
            continue

        summaries.append(summary)
        # retry 闭环：成功后从 failed_paths 移除，下次 backfill 不再 known_failed skip
        if str(path) in stats["failed_paths"]:
            stats["failed_paths"].remove(str(path))
        source_index["sources"][source]["indexed"] += 1
        stats["indexed"] += 1
        stats["last_processed_path"] = str(path)
        stats["last_processed_mtime"] = modified_at

    remaining = 0
    if stats["indexed"] < batch_size:
        for _, item in candidates[int(stats["considered"]) :]:
            path = item.path
            status = existing_summary_status(existing_index.get(str(path)), path, args.backfill_refresh_existing)
            if status in {"missing", "stale", "stale_legacy"}:
                remaining += 1
                break
    stats["completed"] = (
        remaining == 0
        and stats["indexed"] < batch_size
    )
    stats["finished_at"] = format_dt(datetime.now(timezone.utc))
    state = update_backfill_state(stats, run_id, args.reset_backfill)
    source_index["backfill"] = {**stats, "state": state}

    summaries, duplicate_count = dedupe_session_summaries(summaries)
    source_index["deduplicated_sessions"] = duplicate_count
    source_index["coverage"] = compute_coverage_metrics(sources, args.include_subagents, existing_index)
    return summaries, source_index


def promote_repeated_tooling(summaries: list[SessionSummary]) -> None:
    buckets: defaultdict[str, list[SessionSummary]] = defaultdict(list)
    for summary in summaries:
        if summary.session_class != "tooling_fix":
            continue
        key_parts = summary.related_skills[:1] or summary.topic_keywords[:2] or [Path(summary.cwd).name or "tooling"]
        buckets["|".join(key_parts)].append(summary)
    for bucket in buckets.values():
        if len(bucket) < 2:
            continue
        for summary in bucket:
            summary.summary_policy = "cluster_candidate"
            summary.promoted = True
            if "同类工具链问题重复出现，已从 aggregate_only 升格为 cluster_candidate" not in summary.noise_reasons:
                summary.noise_reasons.append("同类工具链问题重复出现，已从 aggregate_only 升格为 cluster_candidate")


GENERIC_LOWER = {item.lower() for item in GENERIC_TOPIC_TERMS}


def weighted_cluster_tokens(summary: SessionSummary) -> dict[str, float]:
    """Build low-noise tokens; generic workflow words do not create links."""
    tokens: dict[str, float] = {}
    for skill in summary.related_skills:
        value = str(skill).strip().lower()
        if value and value not in GENERIC_LOWER:
            tokens[f"skill:{value}"] = 3.0
    for keyword in summary.topic_keywords:
        value = str(keyword).strip().lower()
        if len(value) >= 2 and value not in GENERIC_LOWER:
            tokens[value] = max(tokens.get(value, 0.0), 1.0)
    cwd_name = Path(summary.cwd).name.strip().lower() if summary.cwd else ""
    if len(cwd_name) >= 3 and cwd_name not in GENERIC_LOWER:
        tokens[f"cwd:{cwd_name}"] = 0.35
    return tokens


def cluster_tokens(summary: SessionSummary) -> set[str]:
    return set(weighted_cluster_tokens(summary))


def weighted_similarity(left: dict[str, float], right: dict[str, float]) -> float:
    keys = set(left) | set(right)
    if not keys:
        return 0.0
    intersection = sum(min(left.get(key, 0.0), right.get(key, 0.0)) for key in keys)
    union = sum(max(left.get(key, 0.0), right.get(key, 0.0)) for key in keys)
    return intersection / union if union else 0.0


def cluster_centroid(cluster: TopicCluster, presence_ratio: float = 0.6) -> dict[str, float]:
    if not cluster.sessions:
        return {}
    count = len(cluster.sessions)
    presence: Counter[str] = Counter()
    totals: defaultdict[str, float] = defaultdict(float)
    for session in cluster.sessions:
        tokens = weighted_cluster_tokens(session)
        presence.update(tokens)
        for token, weight in tokens.items():
            totals[token] += weight
    required = max(1, int(count * presence_ratio + 0.999999))
    return {
        token: totals[token] / count
        for token, appearances in presence.items()
        if appearances >= required
    }


def cluster_similarity(summary: SessionSummary, cluster: TopicCluster) -> float:
    return weighted_similarity(weighted_cluster_tokens(summary), cluster_centroid(cluster))


def cluster_membership_metrics(summary: SessionSummary, cluster: TopicCluster) -> tuple[float, float, float]:
    candidate = weighted_cluster_tokens(summary)
    pairwise = [weighted_similarity(candidate, weighted_cluster_tokens(item)) for item in cluster.sessions]
    if not pairwise:
        return 0.0, 0.0, 0.0
    return weighted_similarity(candidate, cluster_centroid(cluster)), sum(pairwise) / len(pairwise), min(pairwise)


def can_join_cluster(summary: SessionSummary, cluster: TopicCluster, min_similarity: float) -> tuple[bool, float]:
    centroid_score, average_score, minimum_score = cluster_membership_metrics(summary, cluster)
    # All three conditions are hard gates. In particular, the minimum member
    # consistency blocks A-B-C bridge chains from snowballing through B.
    allowed = (
        centroid_score >= min_similarity
        and average_score >= min_similarity * 0.9
        and minimum_score >= min_similarity * 0.65
    )
    return allowed, (centroid_score * 0.5 + average_score * 0.35 + minimum_score * 0.15)


def cluster_candidate(summary: SessionSummary) -> bool:
    # subagent 是主会话的子任务，内容高度重叠主会话；主会话已代表主题进聚类，
    # subagent 进聚类只会 flood/重复。subagent 仍写 summary + raw-backup 原文，只是不进聚类/dream。
    if summary.source_variant == "claude_subagent":
        return False
    return summary.summary_policy in {"summarize_candidate", "cluster_candidate"}


def cluster_member_keys(cluster: TopicCluster) -> list[str]:
    """Return the exact, order-independent membership used for revisions."""
    return sorted(
        f"{summary.source}:{summary.session_id or hashlib.sha256(summary.transcript_path.encode('utf-8', errors='replace')).hexdigest()[:16]}"
        for summary in cluster.sessions
    )


def assign_cluster_identity(cluster: TopicCluster) -> None:
    """Separate stable topic/lineage identity from the mutable member revision."""
    semantic_seed = json.dumps(
        {
            "skills": cluster.related_skills[:3],
            "keywords": sorted(cluster_centroid(cluster))[:8],
            "title": cluster.title,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    cluster.semantic_digest = hashlib.sha256(semantic_seed.encode("utf-8")).hexdigest()
    member_keys = cluster_member_keys(cluster)
    cluster.member_digest = hashlib.sha256(
        json.dumps(member_keys, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    cluster.revision = f"rev-{cluster.member_digest}"

    slug = safe_slug(cluster.title)
    cluster.topic_key = f"topic-{cluster.semantic_digest[:16]}-{slug}"
    # The first deterministic member is a lineage anchor, not a digest of the
    # complete membership. Appending members therefore changes the revision but
    # not the cluster id, while equal-topic shards still receive distinct ids.
    anchor = member_keys[0] if member_keys else cluster.topic_key
    lineage_digest = hashlib.sha256(anchor.encode("utf-8", errors="replace")).hexdigest()
    cluster.cluster_id = f"clu-{cluster.semantic_digest[:16]}-{lineage_digest}-{slug}"


def _normalized_hex_digest(raw: Any) -> str:
    value = str(raw or "").strip().lower()
    if value.startswith("sha256:"):
        value = value.split(":", 1)[1]
    return (
        value
        if len(value) in {16, 64}
        and all(character in "0123456789abcdef" for character in value)
        else ""
    )


def _persisted_cluster_semantic_prefix(record: dict[str, Any]) -> str:
    digest = _normalized_hex_digest(record.get("semantic_digest"))
    if digest:
        return digest
    topic_match = re.match(r"^topic-([0-9a-f]{16})-", str(record.get("topic_key") or ""))
    if topic_match:
        return topic_match.group(1)
    cluster_id = str(record.get("cluster_id") or "")
    legacy_match = LEGACY_MEMBER_BOUND_CLUSTER_ID.match(cluster_id)
    if legacy_match:
        return legacy_match.group("semantic")
    stable_match = STABLE_CLUSTER_ID.match(cluster_id)
    return stable_match.group("semantic") if stable_match else ""


def _persisted_cluster_member_keys(record: dict[str, Any]) -> set[str]:
    sessions = record.get("sessions")
    if not isinstance(sessions, list):
        return set()
    keys: set[str] = set()
    for session in sessions:
        if not isinstance(session, dict):
            continue
        source = str(session.get("source") or "").strip()
        session_id = str(session.get("session_id") or "").strip()
        if source and session_id:
            keys.add(f"{source}:{session_id}")
    return keys


def reconcile_cluster_identities(
    clusters: list[TopicCluster],
    previous_clusters: Iterable[dict[str, Any]],
) -> set[int]:
    """Carry v2 lineage ids forward and expose one-time aliases for legacy ids."""
    previous = [item for item in previous_clusters if isinstance(item, dict)]
    candidates: list[tuple[int, float, str, int, int]] = []
    for current_index, cluster in enumerate(clusters):
        current_keys = set(cluster_member_keys(cluster))
        for previous_index, record in enumerate(previous):
            prefix = _persisted_cluster_semantic_prefix(record)
            if not prefix or not cluster.semantic_digest.startswith(prefix):
                continue
            previous_keys = _persisted_cluster_member_keys(record)
            overlap = len(current_keys & previous_keys)
            if not overlap:
                continue
            union_size = len(current_keys | previous_keys)
            similarity = overlap / union_size if union_size else 0.0
            candidates.append(
                (
                    overlap,
                    similarity,
                    str(record.get("cluster_id") or ""),
                    current_index,
                    previous_index,
                )
            )

    matched_current: set[int] = set()
    matched_previous: set[int] = set()
    inherited_v2_ids: set[int] = set()
    for _, _, _, current_index, previous_index in sorted(
        candidates,
        key=lambda item: (-item[0], -item[1], item[2], clusters[item[3]].cluster_id),
    ):
        if current_index in matched_current or previous_index in matched_previous:
            continue
        matched_current.add(current_index)
        matched_previous.add(previous_index)
        cluster = clusters[current_index]
        record = previous[previous_index]
        previous_id = str(record.get("cluster_id") or "").strip()
        aliases = (
            {
                item.strip()
                for item in record.get("legacy_cluster_ids", [])
                if isinstance(item, str) and item.strip()
            }
            if isinstance(record.get("legacy_cluster_ids"), list)
            else set()
        )
        if (
            record.get("id_schema") == CLUSTER_ID_SCHEMA
            and STABLE_CLUSTER_ID.match(previous_id)
        ):
            cluster.cluster_id = previous_id
            inherited_v2_ids.add(current_index)
        elif previous_id and previous_id != cluster.cluster_id:
            # Old member-bound ids deliberately change once during migration;
            # retaining the alias keeps reports and audit trails resolvable.
            aliases.add(previous_id)
        cluster.legacy_cluster_ids = sorted(aliases)
    return inherited_v2_ids


def ensure_unique_cluster_ids(
    clusters: list[TopicCluster],
    inherited_v2_ids: set[int] | None = None,
) -> None:
    """Resolve split/corrupt-history collisions without displacing inherited ids."""
    preferred = inherited_v2_ids or set()
    occupied: set[str] = set()
    order = sorted(
        range(len(clusters)),
        key=lambda index: (
            index not in preferred,
            clusters[index].cluster_id,
            clusters[index].member_digest,
        ),
    )
    for index in order:
        cluster = clusters[index]
        if cluster.cluster_id not in occupied:
            occupied.add(cluster.cluster_id)
            continue
        slug = safe_slug(cluster.title)
        attempt = 0
        while cluster.cluster_id in occupied:
            disambiguator = hashlib.sha256(
                f"{cluster.cluster_id}\0{cluster.member_digest}\0{attempt}".encode(
                    "utf-8", errors="replace"
                )
            ).hexdigest()
            cluster.cluster_id = f"clu-{cluster.semantic_digest[:16]}-{disambiguator}-{slug}"
            attempt += 1
        occupied.add(cluster.cluster_id)


def _cluster_is_generic(cluster: TopicCluster) -> bool:
    """簇内每个成员的 token 全属泛词集合 → 纯泛词簇（合并会致桥接雪球，跳过）。"""
    for session in cluster.sessions:
        tokens = {token.lower() for token in weighted_cluster_tokens(session)}
        if tokens and not tokens.issubset(GENERIC_LOWER):
            return False
    return True


def _merge_similar_clusters(
    clusters: list[TopicCluster], min_similarity: float, cluster_cap: int
) -> list[TopicCluster]:
    """同质簇合并：质心相似度超阈值的簇合并 sessions，避免同主题裂成多簇。

    - 跳过纯泛词簇（防桥接雪球，保护「泛词不聚巨型」语义）；
    - 合并后不超 ``cluster_cap``（保护大簇确定性分片）；
    - 按成员数降序贪心并入已合并集（大树吸小树，结果稳定）。
    """
    merge_threshold = max(min_similarity, 0.55)
    merged: list[TopicCluster] = []
    for cluster in sorted(clusters, key=lambda item: (-len(item.sessions), item.title)):
        if _cluster_is_generic(cluster) or not cluster.sessions:
            merged.append(cluster)
            continue
        centroid = cluster_centroid(cluster)
        host = None
        for candidate in merged:
            if _cluster_is_generic(candidate) or not candidate.sessions:
                continue
            if len(candidate.sessions) >= cluster_cap:
                continue
            if weighted_similarity(centroid, cluster_centroid(candidate)) >= merge_threshold:
                host = candidate
                break
        if host is None or len(host.sessions) + len(cluster.sessions) > cluster_cap:
            merged.append(cluster)
        else:
            host.sessions.extend(cluster.sessions)
    return merged


def build_clusters(
    summaries: list[SessionSummary],
    min_similarity: float = 0.45,
    max_cluster_size: int = DEFAULT_MAX_CLUSTER_SIZE,
    previous_clusters: Iterable[dict[str, Any]] | None = None,
) -> list[TopicCluster]:
    promote_repeated_tooling(summaries)
    cluster_cap = max(1, int(max_cluster_size))
    clusters: list[TopicCluster] = []
    candidates = sorted(
        (summary for summary in summaries if cluster_candidate(summary)),
        key=lambda item: (item.source, item.session_id, item.started_at, item.transcript_path),
    )

    for summary in candidates:
        best: TopicCluster | None = None
        best_score = 0.0
        for cluster in clusters:
            if len(cluster.sessions) >= cluster_cap:
                continue
            allowed, score = can_join_cluster(summary, cluster, min_similarity)
            if allowed and score > best_score:
                best_score = score
                best = cluster
        if best is not None:
            best.sessions.append(summary)
        else:
            title_seed = summary.related_skills[0] if summary.related_skills else (summary.topic_keywords[0] if summary.topic_keywords else summary.topic_title)
            clusters.append(TopicCluster(cluster_id=safe_slug(str(title_seed)), title=str(title_seed), sessions=[summary]))

    clusters = _merge_similar_clusters(clusters, min_similarity, cluster_cap)

    for cluster in clusters:
        keyword_counter = Counter()
        skill_counter = Counter()
        source_counter = Counter()
        stage_counter = Counter()
        for summary in cluster.sessions:
            keyword_counter.update(summary.topic_keywords)
            skill_counter.update(summary.related_skills)
            source_counter.update([summary.source])
            stage_counter.update([summary.work_stage])
        cluster.topic_keywords = [item for item, _ in keyword_counter.most_common(10)]
        cluster.related_skills = [item for item, _ in skill_counter.most_common(6)]
        cluster.sources = [item for item, _ in source_counter.most_common()]
        cluster.work_stages = [item for item, _ in stage_counter.most_common()]
        cluster.title = choose_cluster_title(cluster)
        assign_cluster_identity(cluster)
        pair_scores = [
            weighted_similarity(weighted_cluster_tokens(left), weighted_cluster_tokens(right))
            for index, left in enumerate(cluster.sessions)
            for right in cluster.sessions[index + 1 :]
        ]
        cluster.cohesion_average = round(sum(pair_scores) / len(pair_scores), 4) if pair_scores else 1.0
        cluster.cohesion_minimum = round(min(pair_scores), 4) if pair_scores else 1.0
        cluster.purity = cluster.cohesion_average
        cluster.uncertainty = round(1.0 - cluster.cohesion_minimum, 4)
        cluster.quality_gate = (
            "deep_eligible"
            if len(cluster.sessions) >= 2
            and cluster.cohesion_average >= 0.55
            and cluster.cohesion_minimum >= 0.30
            and bool(cluster.related_skills or len(cluster.topic_keywords) >= 2)
            and any(summary.evidence_snippets for summary in cluster.sessions)
            else "observe_only"
        )
        # Size is a bounded confidence signal, never a linear reward. A large
        # low-purity cluster must not outrank a smaller coherent task chain.
        cluster.score = min(
            100,
            round(cluster.cohesion_average * 40)
            + round(cluster.cohesion_minimum * 20)
            + min(len(cluster.sessions), 8) * 3
            + min(len(cluster.sources), 2) * 4
            + min(len(set(cluster.work_stages)), 4) * 2
            + min(sum(bool(s.evidence_snippets) for s in cluster.sessions), 6) * 2,
        )
        cluster.reasons = build_cluster_reasons(cluster)
    inherited_v2_ids = (
        reconcile_cluster_identities(clusters, previous_clusters)
        if previous_clusters is not None
        else set()
    )
    ensure_unique_cluster_ids(clusters, inherited_v2_ids)
    return sorted(clusters, key=lambda item: (-item.score, item.cluster_id))


def build_cluster_reasons(cluster: TopicCluster) -> list[str]:
    reasons = []
    if len(cluster.sessions) >= 2:
        reasons.append(f"包含 {len(cluster.sessions)} 个相关 session")
    if len(cluster.sources) >= 2:
        reasons.append(f"跨来源协作：{', '.join(cluster.sources)}")
    if cluster.related_skills:
        reasons.append(f"反复关联核心 Skill：{', '.join(cluster.related_skills[:4])}")
    if cluster.topic_keywords:
        reasons.append(f"共享关键词：{', '.join(cluster.topic_keywords[:6])}")
    if len(set(cluster.work_stages)) >= 2:
        reasons.append(f"工作阶段递进：{', '.join(cluster.work_stages[:5])}")
    if any(summary.promoted for summary in cluster.sessions):
        reasons.append("存在重复工具链问题，已按升格规则纳入聚类")
    return reasons or ["主题关键词和工作目录存在连续性"]


def choose_cluster_title(cluster: TopicCluster) -> str:
    keywords = set(cluster.topic_keywords)
    if {"取证", "权利基础", "侵权", "侵权比对"} & keywords:
        return "视频侵权证据整理与比对流程演进"
    generic_title_hits = {"error", "失败", "路径", "OCR", "合同", "发布"} & keywords
    if len(generic_title_hits) >= 2 and len(cluster.sessions) >= 8:
        return "法律 Skill 运维与内容沉淀聚合"
    if "self-evolve" in cluster.related_skills and {"SessionEnd", "Dream Sweep", "hook", "scheduler_run"} & keywords:
        return "Self Evolve 机制迭代"
    if cluster.related_skills:
        return f"{cluster.related_skills[0]} 长周期演进"
    if cluster.topic_keywords:
        return f"{cluster.topic_keywords[0]} 主题演进"
    return "未命名主题演进"


def session_summary_path(summary: SessionSummary) -> Path:
    dt = parse_time(summary.started_at)
    stamp = dt.astimezone().strftime("%y%m%d") if dt else now_stamp()
    month_bucket = stamp[:4]
    return SESSION_SUMMARY_DIR / month_bucket / f"{summary.source}_{stamp}_{safe_slug(summary.session_id, 'session')}.json"


def write_json(path: Path, data: Any) -> None:
    """Atomically replace one JSON document."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        Path(temporary).replace(path)
    finally:
        try:
            Path(temporary).unlink()
        except FileNotFoundError:
            pass


def _fsync_directory(path: Path) -> None:
    """fsync 目录条目，保证新建子目录与 rename 在崩溃后仍可见。"""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _copy_file_atomic(src: Path, dest: Path) -> None:
    """流式 cp + fsync 文件 + rename + fsync 目录，原子发布无损备份。

    no-clobber 由调用方预检；本函数在目标不存在或需覆盖时执行 cp。
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{dest.name}.", dir=str(dest.parent))
    try:
        with os.fdopen(fd, "wb") as out_handle, src.open("rb") as in_handle:
            shutil.copyfileobj(in_handle, out_handle)
            out_handle.flush()
            os.fsync(out_handle.fileno())
        Path(temporary).replace(dest)
    finally:
        try:
            Path(temporary).unlink()
        except FileNotFoundError:
            pass
    try:
        _fsync_directory(dest.parent)
    except OSError:
        pass


def archive_raw_session(summary: SessionSummary) -> str:
    """把会话原文 jsonl 备份到 RAW_SESSIONS_DIR，作为 CC 删除原文后的双保险。

    返回四态之一：
    - ``source_missing``：原文已不存在（可能已被 CC 清理），保留已有备份不删除；
    - ``skipped``：目标已存在且与源同 size（幂等，原文未变）；
    - ``updated``：目标已存在但内容不同（原文被追加/修改），已覆盖更新；
    - ``archived``：目标不存在，首次归档成功。
    出错返回 ``error``，不中断整体索引。
    """
    src = Path(summary.transcript_path) if summary.transcript_path else None
    if not src or not src.exists():
        return "source_missing"
    variant = summary.source_variant or summary.source or "unknown"
    dt = parse_time(summary.started_at)
    stamp = dt.astimezone().strftime("%y%m%d") if dt else now_stamp()
    dest = RAW_SESSIONS_DIR / variant / stamp[:4] / src.name
    already_existed = dest.exists()
    if already_existed:
        try:
            if dest.stat().st_size == src.stat().st_size:
                return "skipped"
        except OSError:
            return "error"
    try:
        _copy_file_atomic(src, dest)
    except OSError:
        return "error"
    return "updated" if already_existed else "archived"


def append_run_event(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(descriptor, "a", encoding="utf-8") as file:
        file.write(json.dumps(event, ensure_ascii=False) + "\n")
        file.flush()
        os.fsync(file.fileno())


@contextmanager
def runtime_index_lock(timeout_seconds: float = 60.0) -> Iterable[None]:
    """Serialize cross-process read/merge/rebuild/write index transactions."""
    DREAMING_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = DREAMING_DIR / ".index.lock"
    if fcntl is not None:
        with lock_path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return

    # Portable fallback for environments without flock.
    claim_path = DREAMING_DIR / ".index.lock.claim"
    started = time.monotonic()
    descriptor: int | None = None
    while descriptor is None:
        try:
            descriptor = os.open(claim_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            try:
                if time.time() - claim_path.stat().st_mtime > max(timeout_seconds * 2, 120):
                    claim_path.unlink()
                    continue
            except OSError:
                pass
            if time.monotonic() - started >= timeout_seconds:
                raise TimeoutError("timed out waiting for runtime index lock")
            time.sleep(0.05)
    try:
        os.write(descriptor, str(os.getpid()).encode())
        yield
    finally:
        os.close(descriptor)
        try:
            claim_path.unlink()
        except FileNotFoundError:
            pass


def runtime_index_paths(args: argparse.Namespace) -> dict[str, str]:
    paths = {
        "source_index": str(DREAMING_DIR / "source-index.json"),
        "session_index": str(DREAMING_DIR / "session-index.json"),
        "timeline_index": str(DREAMING_DIR / "timeline-index.json"),
        "topic_clusters": str(DREAMING_DIR / "topic-clusters.json"),
    }
    if args.index_mode == "backfill":
        paths["backfill_state"] = str(BACKFILL_STATE_PATH)
    return paths


def load_persisted_clusters() -> list[dict[str, Any]]:
    """Load either the historical list shape or a future wrapped shape."""
    payload = read_json(DREAMING_DIR / "topic-clusters.json", [])
    if isinstance(payload, dict):
        payload = payload.get("clusters", [])
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def load_persisted_summaries() -> list[SessionSummary]:
    """Recover the existing full index, including pre-v0.7 summary shards."""
    candidates: list[SessionSummary] = []
    payload = read_json(DREAMING_DIR / "session-index.json", [])
    if isinstance(payload, dict):
        payload = payload.get("sessions", [])
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                parsed = summary_from_dict(item)
                if parsed is not None:
                    candidates.append(parsed)

    # Older runs overwrote session-index.json but left stable per-session shards.
    # Unioning those shards repairs the first post-upgrade transaction.
    for path in summary_json_paths():
        item = read_json(path, {})
        if not isinstance(item, dict):
            continue
        parsed = summary_from_dict(item)
        if parsed is not None:
            candidates.append(parsed)
    return dedupe_session_summaries(candidates)[0]


def stable_summary_key(summary: SessionSummary) -> tuple[str, str]:
    identity = summary.session_id.strip()
    if not identity:
        identity = "path-" + hashlib.sha256(
            summary.transcript_path.encode("utf-8", errors="replace")
        ).hexdigest()[:16]
    return summary.source, identity


def merge_summary_sets(
    existing: Iterable[SessionSummary],
    incoming: Iterable[SessionSummary],
) -> tuple[list[SessionSummary], dict[str, int]]:
    """Merge by stable source/session id; the current batch updates old records."""
    previous = {stable_summary_key(item): item for item in dedupe_session_summaries(existing)[0]}
    incoming_items = dedupe_session_summaries(incoming)[0]
    added = updated = 0
    for item in incoming_items:
        key = stable_summary_key(item)
        if key in previous:
            updated += 1
        else:
            added += 1
        previous[key] = item
    merged = sorted(
        previous.values(),
        key=lambda item: (item.started_at or "", item.source, item.session_id, item.transcript_path),
    )
    return merged, {
        "batch_session_count": len(incoming_items),
        "merged_session_count": len(merged),
        "added_session_count": added,
        "updated_session_count": updated,
        "preserved_session_count": len(merged) - added - updated,
    }


def serialize_clusters(clusters: list[TopicCluster]) -> list[dict[str, Any]]:
    return [
        {
            "id_schema": CLUSTER_ID_SCHEMA,
            "cluster_id": cluster.cluster_id,
            "topic_key": cluster.topic_key,
            "semantic_digest": cluster.semantic_digest,
            "member_digest": cluster.member_digest,
            "revision": cluster.revision,
            "legacy_cluster_ids": cluster.legacy_cluster_ids,
            "title": cluster.title,
            "score": cluster.score,
            "topic_keywords": cluster.topic_keywords,
            "related_skills": cluster.related_skills,
            "sources": cluster.sources,
            "work_stages": cluster.work_stages,
            "reasons": cluster.reasons,
            "analysis_layer": "deterministic_index",
            "analysis_status": "indexed",
            "cohesion_average": cluster.cohesion_average,
            "cohesion_minimum": cluster.cohesion_minimum,
            "purity": cluster.purity,
            "uncertainty": cluster.uncertainty,
            "quality_gate": cluster.quality_gate,
            "evidence": [
                {
                    "evidence_id": evidence_id(summary.session_id, snippet),
                    "source_session_id_hash": hashlib.sha256(
                        summary.session_id.encode("utf-8", errors="replace")
                    ).hexdigest()[:16],
                    "text": compact_text(snippet, 220),
                }
                for summary in cluster.sessions
                for snippet in summary.evidence_snippets[:2]
            ][:16],
            "sessions": [
                {
                    "source": summary.source,
                    "source_variant": summary.source_variant,
                    "session_id": summary.session_id,
                    "started_at": summary.started_at,
                    "cwd_label": summary.cwd_label,
                    "topic_title": summary.topic_title,
                    "session_class": summary.session_class,
                    "summary_policy": summary.summary_policy,
                    "work_stage": summary.work_stage,
                }
                for summary in cluster.sessions
            ],
        }
        for cluster in clusters
    ]


def update_runtime_indexes(
    summaries: list[SessionSummary],
    source_index: dict[str, Any],
    args: argparse.Namespace,
    run_id: str,
) -> tuple[dict[str, str], list[SessionSummary], list[TopicCluster]]:
    """Merge and rebuild all materialized indexes in one locked transaction."""
    similarity = max(0.05, min(0.95, float(getattr(args, "cluster_similarity", 0.45))))
    cluster_cap = max(1, int(getattr(args, "max_cluster_size", DEFAULT_MAX_CLUSTER_SIZE)))
    with runtime_index_lock():
        existing = load_persisted_summaries()
        previous_clusters = load_persisted_clusters()
        merged, merge_stats = merge_summary_sets(existing, summaries)
        clusters = build_clusters(
            merged,
            min_similarity=similarity,
            max_cluster_size=cluster_cap,
            previous_clusters=previous_clusters,
        )
        timeline_index = build_timeline_index(merged, clusters, args)
        paths = runtime_index_paths(args)

        SESSION_SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
        for summary in summaries:
            write_json(session_summary_path(summary), asdict(summary))
        # raw-backup 对 merged 全集（新采 + 已有），no-clobber 幂等补全历史原文
        raw_backup_stats: dict[str, int] = defaultdict(int)
        for summary in merged:
            raw_backup_stats[archive_raw_session(summary)] += 1

        materialized_source_index = dict(source_index)
        materialized_source_index.update(
            {
                "run_id": run_id,
                "mode": args.mode,
                "index_mode": args.index_mode,
                "max_sessions": args.max_sessions,
                "max_cluster_size": cluster_cap,
                "index_scope": "merged_history",
                "merge": merge_stats,
                "raw_backup": dict(raw_backup_stats),
            }
        )
        write_json(Path(paths["source_index"]), materialized_source_index)
        write_json(Path(paths["session_index"]), [asdict(summary) for summary in merged])
        write_json(Path(paths["timeline_index"]), timeline_index)
        write_json(Path(paths["topic_clusters"]), serialize_clusters(clusters))
    return paths, merged, clusters


def write_runtime_indexes(
    summaries: list[SessionSummary],
    clusters: list[TopicCluster],
    source_index: dict[str, Any],
    args: argparse.Namespace,
    run_id: str,
) -> dict[str, str]:
    """Compatibility wrapper; cluster materialization always uses the merged set."""
    del clusters
    paths, _, _ = update_runtime_indexes(summaries, source_index, args, run_id)
    return paths



def build_timeline_index(summaries: list[SessionSummary], clusters: list[TopicCluster], args: argparse.Namespace) -> dict[str, Any]:
    by_day: defaultdict[str, list[SessionSummary]] = defaultdict(list)
    class_counter = Counter()
    source_counter = Counter()
    stage_counter = Counter()
    for summary in summaries:
        by_day[date_key(summary.started_at)].append(summary)
        class_counter.update([summary.session_class])
        source_counter.update([summary.source])
        stage_counter.update([summary.work_stage])
    return {
        "generated_at": format_dt(datetime.now(timezone.utc)),
        "index_scope": "merged_history",
        "requested_since": "all" if args.index_mode == "backfill" else args.since,
        "session_count": len(summaries),
        "cluster_count": len(clusters),
        "by_class": dict(class_counter),
        "by_source": dict(source_counter),
        "by_stage": dict(stage_counter),
        "days": [
            {
                "date": day,
                "count": len(items),
                "classes": dict(Counter(item.session_class for item in items)),
                "top_titles": [item.topic_title for item in items[:5]],
            }
            for day, items in sorted(by_day.items())
            if day
        ],
    }


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        safe_row = [str(cell).replace("\n", " ").replace("|", "\\|") for cell in row]
        lines.append("| " + " | ".join(safe_row) + " |")
    return "\n".join(lines)


def render_timeline_report(summaries: list[SessionSummary], clusters: list[TopicCluster], args: argparse.Namespace) -> str:
    class_counter = Counter(summary.session_class for summary in summaries)
    source_counter = Counter(summary.source for summary in summaries)
    stage_counter = Counter(summary.work_stage for summary in summaries)
    substantive_count = sum(1 for summary in summaries if summary.summary_policy in {"summarize_candidate", "cluster_candidate"})
    index_only_count = sum(1 for summary in summaries if summary.summary_policy == "index_only")

    cluster_rows = [
        [
            cluster.title,
            str(len(cluster.sessions)),
            ", ".join(cluster.sources),
            ", ".join(cluster.related_skills[:3]) or "-",
            ", ".join(cluster.work_stages[:4]) or "-",
            "; ".join(cluster.reasons[:2]),
        ]
        for cluster in clusters
    ]
    day_rows = []
    for day, count in sorted(Counter(date_key(summary.started_at) for summary in summaries if summary.started_at).items()):
        day_items = [summary for summary in summaries if date_key(summary.started_at) == day]
        classes = Counter(item.session_class for item in day_items)
        day_rows.append([day, str(count), ", ".join(f"{k}:{v}" for k, v in classes.most_common(4)), day_items[0].topic_title if day_items else ""])

    return "\n".join(
        [
            f"# {now_stamp()} Timeline Dream Sweep 报告",
            "",
            "## 基本范围",
            "",
            f"- 时间范围：最近 `{args.since}`",
            f"- 模式：`{args.mode}`",
            f"- Session 数量：{len(summaries)}",
            f"- 可进入主题聚类/总结候选：{substantive_count}",
            f"- 只建薄索引：{index_only_count}",
            f"- 来源分布：{', '.join(f'{k}:{v}' for k, v in source_counter.most_common()) or '无'}",
            f"- 分类分布：{', '.join(f'{k}:{v}' for k, v in class_counter.most_common()) or '无'}",
            f"- 阶段分布：{', '.join(f'{k}:{v}' for k, v in stage_counter.most_common()) or '无'}",
            "",
            "## 时间线概览",
            "",
            markdown_table(["日期", "Session", "分类", "代表主题"], day_rows) if day_rows else "暂无可用 session。",
            "",
            "## 主题集群",
            "",
            markdown_table(["主题", "Session", "来源", "关联 Skill", "阶段", "关联理由"], cluster_rows) if cluster_rows else "未形成达到阈值的主题集群。",
            "",
            "## 维护背景",
            "",
            f"- `maintenance/git_ops/software_update` 默认不进入 Dream 报告正文；本次薄索引数量为 {index_only_count}。",
            "- 若同类工具链失败重复出现，脚本会把 `tooling_fix` 从聚合观察升格为聚类候选。",
            "",
            "## 待用户确认",
            "",
            "- 哪些主题需要进入正式 Skill 升级建议。",
            "- 哪些主题可以转成文章草稿。",
            "- 哪些聚类只是阶段性噪音，应在后续 review-log 中降权。",
            "",
        ]
    )


def cluster_evidence(cluster: TopicCluster, limit: int = 8) -> list[str]:
    evidence = []
    for summary in cluster.sessions:
        for snippet in summary.evidence_snippets:
            if snippet and snippet not in evidence:
                evidence.append(snippet)
            if len(evidence) >= limit:
                return evidence
    return evidence


def render_cluster_evidence_packet(cluster: TopicCluster) -> str:
    rows = [
        [
            date_key(summary.started_at),
            summary.source,
            summary.source_variant,
            summary.session_class,
            summary.work_stage,
            summary.topic_title,
        ]
        for summary in cluster.sessions
    ]
    evidence = cluster_evidence(cluster, limit=8)
    return "\n".join(
        [
            f"# 确定性 Cluster 证据包：{cluster.title}",
            "",
            "> 本文件只包含程序化索引与脱敏证据，不是深度分析结论，不代表人工同意升级任何 Skill。",
            "",
            f"- Cluster ID：`{cluster.cluster_id}`",
            f"- Session：{len(cluster.sessions)}",
            f"- 平均一致性：{cluster.cohesion_average:.4f}",
            f"- 最低成员一致性：{cluster.cohesion_minimum:.4f}",
            f"- 纯度：{cluster.purity:.4f}",
            f"- 不确定性：{cluster.uncertainty:.4f}",
            f"- 深度分析门控：`{cluster.quality_gate}`",
            f"- 关联 Skill：{', '.join(cluster.related_skills) or '未识别'}",
            f"- 关键词：{', '.join(cluster.topic_keywords) or '未识别'}",
            "",
            "## Session 索引",
            "",
            markdown_table(["日期", "来源", "适配器", "分类", "阶段", "主题"], rows),
            "",
            "## 脱敏证据片段",
            "",
            "\n".join(f"- {item}" for item in evidence) if evidence else "- 无可安全展示片段。",
            "",
            "## 下一层分析状态",
            "",
            "- `analysis_unavailable`：确定性 index 不调用 LLM；如需深度分析，请显式运行 `deep_dream.py`。",
            "- 人工决策：`pending`。",
            "",
        ]
    )


def write_reports(summaries: list[SessionSummary], clusters: list[TopicCluster], args: argparse.Namespace) -> dict[str, Any]:
    """Publish deterministic index packets through the mandatory privacy gate.

    ``--generate`` is retained for CLI compatibility, but no longer fabricates
    upgrade directions, articles, or context conclusions from fixed templates.
    """
    selected_clusters = [cluster for cluster in clusters if len(cluster.sessions) >= args.min_cluster_size]
    source_ids = [summary.session_id for summary in summaries]
    timeline_path = TIMELINE_OUTPUT_DIR / f"{now_stamp()}_{safe_slug(args.since)}_timeline-index.md"
    timeline_result = write_review_artifact(
        timeline_path,
        render_timeline_report(summaries, selected_clusters, args).replace(
            "Timeline Dream Sweep 报告", "Timeline Dream Sweep 确定性索引"
        ),
        artifact_id=f"timeline-{now_stamp()}-{safe_slug(args.since)}",
        source_session_ids=source_ids,
    )

    packet_paths: list[str] = []
    privacy_results: list[dict[str, Any]] = [timeline_result]
    for cluster in selected_clusters[: args.max_reports]:
        path = DREAM_OUTPUT_DIR / f"{now_stamp()}_{safe_slug(cluster.cluster_id)}_cluster-packet.md"
        result = write_review_artifact(
            path,
            render_cluster_evidence_packet(cluster),
            artifact_id=f"packet-{cluster.cluster_id[:40]}",
            source_session_ids=[summary.session_id for summary in cluster.sessions],
        )
        privacy_results.append(result)
        if result.get("status") == "published":
            packet_paths.append(str(path))

    return {
        "analysis_layer": "deterministic_index",
        "deprecation_notice": "--generate 仅发布确定性索引/证据包；深度分析请显式运行 deep_dream.py",
        "timeline_report": str(timeline_path) if timeline_result.get("status") == "published" else "",
        "dream_reports": packet_paths,
        "upgrade_directions": [],
        "articles": [],
        "context_updates": [],
        "privacy_results": privacy_results,
    }


def build_result(
    summaries: list[SessionSummary],
    clusters: list[TopicCluster],
    paths: dict[str, str],
    reports: dict[str, Any] | None,
    args: argparse.Namespace,
    run_id: str,
) -> dict[str, Any]:
    selected_clusters = [cluster for cluster in clusters if len(cluster.sessions) >= args.min_cluster_size]
    return {
        "run_id": run_id,
        "mode": args.mode,
        "index_mode": args.index_mode,
        "since": "all" if args.index_mode == "backfill" else args.since,
        "session_count": len(summaries),
        "cluster_count": len(clusters),
        "selected_cluster_count": len(selected_clusters),
        "by_class": dict(Counter(summary.session_class for summary in summaries)),
        "by_source": dict(Counter(summary.source for summary in summaries)),
        "runtime_indexes": paths,
        "reports": reports or {},
        "backfill": read_json(BACKFILL_STATE_PATH, {}) if args.index_mode == "backfill" else {},
    }


def normalize_mode(args: argparse.Namespace) -> str:
    if args.generate:
        return "generate"
    if args.dry_run:
        return "dry-run"
    return args.mode or "dry-run"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Self Evolve Timeline Dream Sweep.")
    parser.add_argument("--since", default="14d", help="Time range, e.g. 7d, 14d, 24h")
    parser.add_argument("--mode", choices=["dry-run", "generate"], default="")
    parser.add_argument("--index-mode", choices=["recent", "backfill"], default="recent", help="recent scans --since; backfill scans older unindexed transcripts in bounded batches")
    parser.add_argument("--dry-run", action="store_true", help="Build indexes and preview only")
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Compatibility flag: publish deterministic timeline/cluster packets; never calls an LLM",
    )
    parser.add_argument(
        "--budget",
        choices=["low", "medium", "high"],
        default="low",
        help="Deprecated compatibility option; does not change deterministic scan scope",
    )
    parser.add_argument("--sources", default="claude,codex", help="Comma-separated sources: claude,codex")
    parser.add_argument("--max-sessions", type=int, default=120)
    parser.add_argument("--max-lines-per-session", type=int, default=5000)
    parser.add_argument("--min-cluster-size", type=int, default=2)
    parser.add_argument("--cluster-similarity", type=float, default=0.45)
    parser.add_argument("--max-cluster-size", type=int, default=DEFAULT_MAX_CLUSTER_SIZE)
    parser.add_argument("--max-reports", type=int, default=8)
    parser.add_argument("--include-subagents", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--backfill-batch-size", type=int, default=200, help="Max unindexed or stale transcripts to summarize per backfill run")
    parser.add_argument("--backfill-order", choices=["newest-first", "oldest-first"], default="newest-first")
    parser.add_argument("--backfill-refresh-existing", action="store_true", help="Re-summarize legacy summaries that lack transcript fingerprints")
    parser.add_argument("--reset-backfill", action="store_true", help="Reset persisted backfill run state before this run")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    try:
        assert_runtime_ready()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    args.mode = normalize_mode(args)
    if args.index_mode == "backfill":
        args.mode = "dry-run"

    # Compatibility only: deterministic indexing has one explicit scan scope.
    # LLM cost/quality budgets are controlled exclusively by deep_dream.py.

    run_id = run_stamp()
    run_log = DREAM_RUN_DIR / f"{run_id}.jsonl"
    append_run_event(
        run_log,
        {
            "event": "started",
            "timestamp": format_dt(datetime.now(timezone.utc)),
            "mode": args.mode,
            "index_mode": args.index_mode,
            "since": "all" if args.index_mode == "backfill" else args.since,
        },
    )

    core_keywords, skills, candidate_catalog_status = collect_core_skill_data()
    if args.index_mode == "backfill":
        summaries, source_index = build_backfill_summaries(args, core_keywords, skills, run_id)
    else:
        summaries, source_index = build_summaries(args, core_keywords, skills)
    source_index["skill_candidate_catalog"] = candidate_catalog_status
    runtime_paths, summaries, clusters = update_runtime_indexes(summaries, source_index, args, run_id)
    reports = write_reports(summaries, clusters, args) if args.mode == "generate" else None

    result = build_result(summaries, clusters, runtime_paths, reports, args, run_id)
    result["skill_candidate_catalog"] = candidate_catalog_status
    append_run_event(run_log, {"event": "completed", "timestamp": format_dt(datetime.now(timezone.utc)), "result": result})

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    elif not args.quiet:
        print(f"[Self Evolve] Dream Sweep {args.mode} 完成")
        print(f"- sessions: {result['session_count']}")
        print(f"- clusters: {result['cluster_count']} / selected: {result['selected_cluster_count']}")
        if reports:
            print(f"- timeline: {reports.get('timeline_report')}")
            for path in reports.get("dream_reports", []):
                print(f"- cluster packet: {path}")
            for path in reports.get("upgrade_directions", []):
                print(f"- upgrade: {path}")
            for path in reports.get("articles", []):
                print(f"- article: {path}")
            for path in reports.get("context_updates", []):
                print(f"- context: {path}")
        else:
            print(f"- indexes: {runtime_paths['timeline_index']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
