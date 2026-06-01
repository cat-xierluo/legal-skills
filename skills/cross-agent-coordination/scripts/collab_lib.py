#!/usr/bin/env python3
"""Shared helpers for cross-agent-coordination scripts."""

from __future__ import annotations

import difflib
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - exercised by users without PyYAML
    yaml = None

DEFAULT_AGENT = "openclaw"
DEFAULT_AGENT_EMAIL_DOMAIN = "agents.local"
DONE_STATUSES = {"done", "resolved", "closed"}
ISSUE_DEPENDENCY_DONE_STATUSES = {"done", "resolved", "closed", "ready", "created"}
DEFAULT_TASK_SOURCE_CANDIDATES = ("docs/TASKS.md", "docs/ISSUES.md", "TASKS.md", "ISSUES.md")
DEFAULT_ISSUE_FILE = DEFAULT_TASK_SOURCE_CANDIDATES[0]
DEFAULT_STATUS_MAP = {
    "⬜": "pending_confirmation",
    "✅": "ready",
    "🟢": "created",
    "[ ]": "todo",
    "[x]": "done",
    "[X]": "done",
}
DEFAULT_AVAILABLE_STATUSES = {"todo", "ready", "created"}
CLAIM_POOL_EMPTY = {"", "-", "unassigned", "pool", "none", "null"}
IGNORED_DIRS = {
    ".claude",
    ".git",
    ".github",
    "assets",
    "config",
    "docs",
    "meta",
    "scripts",
    "skill",
    "source-material",
    "templates",
}

DEFAULT_TASK_TYPES = {
    "研究": {
        "aliases": ["research"],
        "description": "信息收集/调研",
        "output_hint": "报告/笔记/清单",
    },
    "写作": {
        "aliases": ["writing"],
        "description": "内容创作",
        "output_hint": "文章/脚本/章节",
    },
    "整合": {
        "aliases": ["integration", "integrate"],
        "description": "多来源材料融合",
        "output_hint": "统一稿/整合报告",
    },
    "审阅": {
        "aliases": ["review"],
        "description": "质量审查/事实核查",
        "output_hint": "审阅意见/修订稿",
    },
    "课程": {
        "aliases": ["course"],
        "description": "课程学习",
        "output_hint": "课程笔记/学习记录",
    },
    "代码": {
        "aliases": ["code"],
        "description": "代码项目",
        "output_hint": "可运行的代码/工具",
    },
    "法律": {
        "aliases": ["legal"],
        "description": "律师业务",
        "output_hint": "方案/文档/分析",
    },
    "实验": {
        "aliases": ["exp"],
        "description": "实验性尝试",
        "output_hint": "验证结果/经验总结",
    },
    "同步": {
        "aliases": ["sync"],
        "description": "知识同步/归档",
        "output_hint": "整理后的文件",
    },
}


def skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


def require_yaml(path: Path) -> None:
    if yaml is None:
        print("❌ 缺少依赖: PyYAML")
        print("   请运行: python3 -m pip install -r scripts/requirements.txt")
        print("   或运行: python3 -m pip install PyYAML")
        raise SystemExit(f"无法读取 YAML 文件: {path}")


def read_yaml(path: Path, *, required: bool = False) -> dict[str, Any]:
    if not path.exists():
        if required:
            raise SystemExit(f"找不到配置文件: {path}")
        return {}
    require_yaml(path)
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"YAML 顶层必须是对象: {path}")
    return data


def load_config(root: Path | str) -> dict[str, Any]:
    root = Path(root).expanduser()
    return read_yaml(root / "config" / "collab.yaml")


def project_config(config: dict[str, Any]) -> dict[str, Any]:
    value = config.get("project", {})
    return value if isinstance(value, dict) else {}


def resolve_project_path(root: Path, value: str, default: str) -> Path:
    raw = value or default
    path = Path(raw).expanduser()
    return path if path.is_absolute() else root / path


def issue_file_path(root: Path, config: dict[str, Any]) -> Path:
    project = project_config(config)
    configured = str(project.get("issue_file") or project.get("task_source_file") or "")
    if configured:
        return resolve_project_path(root, configured, DEFAULT_ISSUE_FILE)
    for candidate in DEFAULT_TASK_SOURCE_CANDIDATES:
        path = resolve_project_path(root, candidate, DEFAULT_ISSUE_FILE)
        if path.exists():
            return path
    return resolve_project_path(root, DEFAULT_ISSUE_FILE, DEFAULT_ISSUE_FILE)


def issue_status_map(config: dict[str, Any]) -> dict[str, str]:
    project = project_config(config)
    configured = project.get("status_map", {})
    result = dict(DEFAULT_STATUS_MAP)
    if isinstance(configured, dict):
        result.update({str(k): str(v) for k, v in configured.items()})
    return result


def available_statuses(config: dict[str, Any]) -> set[str]:
    project = project_config(config)
    configured = project.get("available_statuses", [])
    if isinstance(configured, list) and configured:
        return {str(item) for item in configured}
    if isinstance(configured, str) and configured.strip():
        return {item.strip() for item in configured.split(",") if item.strip()}
    return set(DEFAULT_AVAILABLE_STATUSES)


def dependency_done_statuses(config: dict[str, Any]) -> set[str]:
    project = project_config(config)
    configured = project.get("dependency_done_statuses", [])
    if isinstance(configured, list) and configured:
        return {str(item) for item in configured}
    if isinstance(configured, str) and configured.strip():
        return {item.strip() for item in configured.split(",") if item.strip()}
    return set(ISSUE_DEPENDENCY_DONE_STATUSES)


def task_context_mode(config: dict[str, Any]) -> str:
    return str(project_config(config).get("task_context_mode", "issues_primary"))


def get_current_agent(config: dict[str, Any], explicit_agent: str = "") -> str:
    if explicit_agent:
        return explicit_agent
    if os.getenv("AGENT_ID"):
        return os.getenv("AGENT_ID", "")
    project = project_config(config)
    if project.get("default_agent"):
        return str(project["default_agent"])
    agent_cfg = config.get("agent", {})
    if isinstance(agent_cfg, dict) and agent_cfg.get("current"):
        return str(agent_cfg["current"])
    return DEFAULT_AGENT


def get_agent_info(config: dict[str, Any], agent: str) -> dict[str, Any]:
    agents = config.get("agents", {})
    return agents.get(agent, {}) if isinstance(agents, dict) else {}


def get_agent_identity(config: dict[str, Any], agent: str) -> dict[str, str]:
    info = get_agent_info(config, agent)
    git_name = info.get("git_name") or info.get("name") or agent
    git_email = info.get("git_email") or info.get("email") or f"{agent}@{DEFAULT_AGENT_EMAIL_DOMAIN}"
    return {
        "id": agent,
        "git_name": str(git_name),
        "git_email": str(git_email),
        "github_user": str(info.get("github_user", "")),
        "token_env": str(info.get("token_env", "")),
    }


def get_token(config: dict[str, Any], agent: str = "") -> str:
    current_agent = get_current_agent(config, agent)
    identity = get_agent_identity(config, current_agent)
    token_env = identity.get("token_env", "")
    if token_env and os.getenv(token_env):
        return os.getenv(token_env, "")
    return os.getenv("GITHUB_TOKEN", "") or str(config.get("github", {}).get("token", ""))


class TaskTypeRegistry:
    def __init__(self, task_types: dict[str, Any]):
        self.task_types = task_types
        self.aliases: dict[str, str] = {}
        for canonical, info in task_types.items():
            self.aliases[canonical] = canonical
            if isinstance(info, dict):
                for alias in info.get("aliases", []) or []:
                    self.aliases[str(alias)] = canonical

    @property
    def canonical_types(self) -> set[str]:
        return set(self.task_types)

    @property
    def alias_values(self) -> set[str]:
        return set(self.aliases)

    def normalize(self, task_type: str) -> str:
        if task_type in self.aliases:
            return self.aliases[task_type]
        allowed = ", ".join(sorted(self.aliases))
        raise SystemExit(f"未知任务类型: {task_type}；可用类型: {allowed}")


def load_task_type_registry(root: Path, config: dict[str, Any] | None = None) -> TaskTypeRegistry:
    config = config or load_config(root)
    project = project_config(config)
    configured = project.get("task_types_file", "config/task-types.yaml")
    project_file = resolve_project_path(root, str(configured), "config/task-types.yaml")
    default_file = skill_root() / "references" / "task-types.yaml"

    task_types = dict(DEFAULT_TASK_TYPES)
    source = project_file if project_file.exists() else default_file
    data = read_yaml(source)
    if isinstance(data.get("task_types"), dict):
        task_types.update(data["task_types"])
    return TaskTypeRegistry(task_types)


def parse_frontmatter(readme: Path) -> dict[str, Any]:
    if not readme.exists():
        return {}
    text = readme.read_text(encoding="utf-8", errors="ignore")
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    raw = parts[1]
    if yaml is not None:
        data = yaml.safe_load(raw) or {}
        return data if isinstance(data, dict) else {}
    data: dict[str, Any] = {}
    for line in raw.splitlines():
        match = re.match(r"\s*([A-Za-z_][\w-]*):\s*(.*?)\s*(?:#.*)?$", line)
        if match:
            data[match.group(1)] = match.group(2).strip().strip("\"'")
    return data


def split_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    if not content.startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content
    data: dict[str, Any] = {}
    if yaml is not None:
        parsed = yaml.safe_load(parts[1]) or {}
        if isinstance(parsed, dict):
            data = parsed
    return data, parts[2].lstrip("\n")


def yaml_scalar(value: Any) -> str:
    if value is None:
        return '""'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if text == "":
        return '""'
    if re.search(r"[:#\[\]{}]|^\s|\s$|^[-?]|^(true|false|null|none)$", text, re.I):
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return text


def dump_frontmatter(data: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in data.items():
        if isinstance(value, list):
            if not value:
                lines.append(f"{key}: []")
            else:
                lines.append(f"{key}:")
                for item in value:
                    lines.append(f"  - {yaml_scalar(item)}")
        else:
            lines.append(f"{key}: {yaml_scalar(value)}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def merge_frontmatter(content: str, fields: dict[str, Any]) -> str:
    existing, body = split_frontmatter(content)
    merged = dict(existing)
    merged.update(fields)
    return dump_frontmatter(merged) + "\n" + body.lstrip("\n")


def render_template(content: str, values: dict[str, Any]) -> str:
    rendered = content
    for key, value in values.items():
        rendered = re.sub(r"{{\s*" + re.escape(key) + r"\s*}}", str(value), rendered)
    return rendered


def parse_field(value: str) -> tuple[str, Any]:
    if "=" not in value:
        raise SystemExit(f"--field 必须使用 key=value 格式: {value}")
    key, raw = value.split("=", 1)
    key = key.strip()
    raw = raw.strip()
    if not re.match(r"^[A-Za-z_][\w-]*$", key):
        raise SystemExit(f"非法字段名: {key}")
    if raw == "[]":
        parsed: Any = []
    elif raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        parsed = [item.strip() for item in inner.split(",") if item.strip()] if inner else []
    elif raw.isdigit():
        parsed = int(raw)
    else:
        parsed = raw
    return key, parsed


def parse_slug(slug: str) -> dict[str, str] | None:
    match = re.match(r"^(?P<id>\d{9})-(?P<type>[^-]+)-(?P<title>.+)$", slug)
    return match.groupdict() if match else None


def strip_slug_prefix(text: str) -> str:
    parts = text.split("-", 2)
    if len(parts) == 3 and re.match(r"^\d{6,9}$", parts[0]):
        return parts[2]
    return text


def sanitize_slug_part(text: str) -> str:
    text = re.sub(r'[\\/:*?"<>|#]+', "-", text.strip())
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"-{2,}", "-", text)
    return text.strip("-")


def is_task_dir(path: Path) -> bool:
    if not path.is_dir() or path.name in IGNORED_DIRS:
        return False
    if parse_slug(path.name):
        return True
    fm = parse_frontmatter(path / "README.md")
    return bool(fm.get("id") or fm.get("slug"))


def iter_task_dirs(root: Path):
    for parent in [root, root / "archive"]:
        if not parent.exists():
            continue
        for item in parent.iterdir():
            if is_task_dir(item):
                yield item


def extract_task_id(readme: Path) -> str:
    fm = parse_frontmatter(readme)
    value = fm.get("id", "")
    return str(value) if re.match(r"^\d{9}$", str(value)) else ""


def get_next_task_id(root: Path, date_str: str | None = None) -> str:
    date_str = date_str or datetime.now().strftime("%y%m%d")
    date_prefix = date_str[2:] if len(date_str) == 8 else date_str
    max_num = 0
    for task_dir in iter_task_dirs(root):
        task_id = extract_task_id(task_dir / "README.md")
        if not task_id:
            match = re.match(rf"^{re.escape(date_prefix)}(\d{{3}})(?:-|$)", task_dir.name)
            task_id = f"{date_prefix}{match.group(1)}" if match else ""
        match = re.match(rf"^{re.escape(date_prefix)}(\d{{3}})$", task_id)
        if match:
            max_num = max(max_num, int(match.group(1)))
    return f"{date_prefix}{max_num + 1:03d}"


def normalize_topic(text: str, registry: TaskTypeRegistry) -> str:
    text = strip_slug_prefix(text)
    for task_type in registry.canonical_types:
        text = text.replace(task_type, "")
    for alias in registry.alias_values:
        text = re.sub(rf"\b{re.escape(alias)}\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"[\W_]+", "", text, flags=re.UNICODE)
    return text.lower()


def char_ngrams(text: str, registry: TaskTypeRegistry, width: int = 2) -> set[str]:
    text = normalize_topic(text, registry)
    if len(text) <= width:
        return {text} if text else set()
    return {text[i : i + width] for i in range(len(text) - width + 1)}


def similarity(query: str, candidate: str, registry: TaskTypeRegistry) -> float:
    query_norm = normalize_topic(query, registry)
    candidate_norm = normalize_topic(candidate, registry)
    if not query_norm or not candidate_norm:
        return 0.0
    sequence_score = difflib.SequenceMatcher(None, query_norm, candidate_norm).ratio()
    query_grams = char_ngrams(query_norm, registry)
    candidate_grams = char_ngrams(candidate_norm, registry)
    overlap_score = 0.0
    if query_grams and candidate_grams:
        overlap_score = len(query_grams & candidate_grams) / len(query_grams | candidate_grams)
    return max(sequence_score, overlap_score)


def as_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if isinstance(value, str):
        stripped = value.strip()
        if stripped == "[]":
            return []
        return [item.strip() for item in stripped.split(",") if item.strip()]
    return [str(value)]


def markdown_heading(line: str) -> tuple[int, str] | None:
    match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
    if not match:
        return None
    return len(match.group(1)), match.group(2).strip()


def normalize_field_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().strip("*")).lower()


def parse_markdown_fields(lines: list[str]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in lines:
        match = re.match(r"^\s*[-*]\s+(?:\*\*)?([^:*：]+?)(?:\*\*)?\s*[:：]\s*(.+?)\s*$", line)
        if not match:
            continue
        key = normalize_field_name(match.group(1))
        value = match.group(2).strip()
        fields[key] = value
    return fields


def parse_markdown_sections(lines: list[str]) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current = ""
    buffer: list[str] = []
    for line in lines:
        heading = markdown_heading(line)
        if heading:
            level, title = heading
            if level >= 4:
                if current:
                    sections[current] = buffer
                current = title
                buffer = []
                continue
        if current:
            buffer.append(line)
    if current:
        sections[current] = buffer
    return {key: "\n".join(value).strip() for key, value in sections.items() if "\n".join(value).strip()}


def detect_agent_id(config: dict[str, Any], text: str) -> str:
    if not text:
        return ""
    haystack = text.lower()
    known_agents: dict[str, set[str]] = {
        "codex": {"codex"},
        "claude_code": {"claude code", "claude-code", "claude_code"},
        "manus": {"manus"},
        "openclaw": {"openclaw", "openclaw"},
        "anygen": {"anygen"},
        "coze": {"coze"},
        "hermes": {"hermes"},
    }
    agents = config.get("agents", {})
    if isinstance(agents, dict):
        for agent_id, info in agents.items():
            tokens = known_agents.setdefault(str(agent_id), {str(agent_id).replace("_", " ").lower(), str(agent_id).lower()})
            if isinstance(info, dict):
                for field in ["name", "github_user", "email", "git_email"]:
                    value = str(info.get(field, "")).strip()
                    if value:
                        tokens.add(value.lower())
    for agent_id, tokens in known_agents.items():
        for token in tokens:
            if token and token in haystack:
                return agent_id
    return ""


def field_value(fields: dict[str, str], names: list[str]) -> str:
    wanted = {normalize_field_name(name) for name in names}
    for key, value in fields.items():
        if key in wanted:
            return value
    return ""


def normalize_issue_type(raw: str, registry: TaskTypeRegistry) -> str:
    if not raw:
        return "-"
    cleaned = re.split(r"[（(]", raw, 1)[0].strip()
    if not cleaned:
        cleaned = raw.strip()
    try:
        return registry.normalize(cleaned)
    except SystemExit:
        return cleaned


def infer_issue_type(title: str, fields: dict[str, str], sections: dict[str, str], registry: TaskTypeRegistry) -> str:
    keys = set(sections)
    lead = field_value(fields, ["lead author", "负责人", "负责"])
    if "调研任务" in keys:
        candidate = "研究"
    elif "审阅维度" in keys or "审阅" in title:
        candidate = "审阅"
    elif "需确定事项" in keys or "术语" in title or "一致性" in title:
        candidate = "整合"
    elif re.search(r"\bch\d+\b", title, flags=re.IGNORECASE) or field_value(fields, ["目标字数"]) or lead:
        candidate = "写作"
    else:
        return "-"
    try:
        return registry.normalize(candidate)
    except SystemExit:
        return candidate


def parse_issue_dependencies(text: str) -> list[str]:
    deps: list[str] = []
    for match in re.finditer(r"(?:Issue\s*)?#\s*(\d+)", text, flags=re.IGNORECASE):
        value = match.group(1)
        if value not in deps:
            deps.append(value)
    return deps


def issue_heading_parts(title: str) -> tuple[str, str, str] | None:
    match = re.match(
        r"^(?:(?P<marker>[\u2610-\u2611\u2705\U0001f7e2⬜✅🟢]|\[[ xX]\])\s+)?"
        r"Issue\s*#(?P<num>\d+)\s*[:：]\s*(?P<title>.+?)\s*$",
        title,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return match.group("marker") or "", match.group("num"), match.group("title").strip()


def issue_summary_from_block(
    root: Path,
    issue_file: Path,
    heading_marker: str,
    number: str,
    title: str,
    lines: list[str],
    config: dict[str, Any],
    registry: TaskTypeRegistry,
) -> dict[str, Any]:
    fields = parse_markdown_fields(lines)
    sections = parse_markdown_sections(lines)
    status = issue_status_map(config).get(heading_marker, heading_marker or "todo")
    raw_type = field_value(fields, ["type", "类型", "task type"])
    task_type = normalize_issue_type(raw_type, registry)
    if task_type == "-":
        task_type = infer_issue_type(title, fields, sections, registry)
    explicit_owner = field_value(fields, ["assignee", "owner", "负责人", "负责", "lead author", "执行者", "委托"])
    agent_from_owner = detect_agent_id(config, explicit_owner)
    agent_from_type = detect_agent_id(config, raw_type)
    agent_from_text = detect_agent_id(config, title)
    assignee = agent_from_owner or agent_from_type or agent_from_text or explicit_owner
    dependency_text = field_value(fields, ["依赖", "dependencies", "depends_on", "depends on"])
    dependencies = parse_issue_dependencies(dependency_text)
    objective = field_value(fields, ["目标", "objective"]) or title
    source_material = field_value(fields, ["素材来源", "来源材料", "source material", "sources"])
    block_text = "\n".join(lines).strip()
    searchable = " ".join([title, task_type, explicit_owner, raw_type, dependency_text, objective, source_material, block_text])
    rel_issue_file = str(issue_file.relative_to(root)) if issue_file.is_relative_to(root) else str(issue_file)
    return {
        "source": "issue",
        "path": str(issue_file),
        "issue_file": rel_issue_file,
        "slug": f"Issue #{number}",
        "id": number,
        "issue_number": number,
        "title": title,
        "status": status,
        "status_marker": heading_marker,
        "type": task_type,
        "assignee": assignee,
        "owner": explicit_owner,
        "dependencies": dependencies,
        "dependency_text": dependency_text,
        "objective": objective,
        "source_material": source_material,
        "sections": sections,
        "fields": fields,
        "searchable": searchable,
    }


def iter_issue_summaries(root: Path, registry: TaskTypeRegistry, config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    config = config or load_config(root)
    issue_file = issue_file_path(root, config)
    if not issue_file.exists():
        return []
    lines = issue_file.read_text(encoding="utf-8", errors="ignore").splitlines()
    starts: list[tuple[int, str, str, str]] = []
    for idx, line in enumerate(lines):
        heading = markdown_heading(line)
        if not heading:
            continue
        parts = issue_heading_parts(heading[1])
        if parts:
            marker, number, title = parts
            starts.append((idx, marker, number, title))
    summaries: list[dict[str, Any]] = []
    for pos, (idx, marker, number, title) in enumerate(starts):
        end = starts[pos + 1][0] if pos + 1 < len(starts) else len(lines)
        block = lines[idx + 1 : end]
        summaries.append(issue_summary_from_block(root, issue_file, marker, number, title, block, config, registry))
    return summaries


def task_summary(task_dir: Path, registry: TaskTypeRegistry) -> dict[str, Any]:
    readme = task_dir / "README.md"
    fm = parse_frontmatter(readme)
    parsed = parse_slug(task_dir.name) or {}
    title = str(fm.get("title") or parsed.get("title") or strip_slug_prefix(task_dir.name))
    raw_type = str(fm.get("type") or parsed.get("type") or "-")
    try:
        task_type = registry.normalize(raw_type)
    except SystemExit:
        task_type = raw_type
    task_id = str(fm.get("id") or parsed.get("id") or "-")
    assignee = str(fm.get("assignee") or fm.get("agent") or "")
    content_sample = ""
    if readme.exists():
        content_sample = "\n".join(readme.read_text(encoding="utf-8", errors="ignore").splitlines()[:100])
    searchable = " ".join([task_dir.name, str(fm.get("slug", "")), title, task_type, content_sample])
    return {
        "source": "task_folder",
        "path": str(task_dir),
        "slug": task_dir.name,
        "id": task_id,
        "title": title,
        "status": str(fm.get("status", "-")),
        "type": task_type,
        "assignee": assignee,
        "dependencies": as_list(fm.get("dependencies")),
        "searchable": searchable,
    }


def iter_project_tasks(root: Path, registry: TaskTypeRegistry, config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    config = config or load_config(root)
    folder_tasks = [task_summary(task_dir, registry) for task_dir in iter_task_dirs(root)]
    issue_tasks = iter_issue_summaries(root, registry, config)
    mode = task_context_mode(config)
    if mode == "task_folders_only":
        return folder_tasks
    if mode == "task_folders_primary":
        return folder_tasks + issue_tasks
    return issue_tasks + folder_tasks


def find_task_by_ref(root: Path, registry: TaskTypeRegistry, task_ref: str, config: dict[str, Any] | None = None) -> dict[str, Any] | None:
    normalized = str(task_ref).strip()
    normalized = re.sub(r"^Issue\s*#?", "", normalized, flags=re.IGNORECASE).strip()
    normalized = normalized.lstrip("#")
    for summary in iter_project_tasks(root, registry, config):
        if (
            summary["id"] == normalized
            or summary["id"] == task_ref
            or summary["slug"] == task_ref
            or summary["slug"].startswith(task_ref)
            or (summary.get("issue_number") and summary.get("issue_number") == normalized)
        ):
            return summary
    return None


def dependencies_satisfied(root: Path, registry: TaskTypeRegistry, dependencies: list[str], config: dict[str, Any] | None = None) -> bool:
    config = config or load_config(root)
    for dep in dependencies:
        task = find_task_by_ref(root, registry, dep, config)
        if not task:
            return False
        done_statuses = dependency_done_statuses(config) if task.get("source") == "issue" else DONE_STATUSES
        if task["status"] not in done_statuses:
            return False
    return True


def assignee_matches(config: dict[str, Any], assignee: str, agent: str, claim_policy: str) -> bool:
    assignee = (assignee or "").strip()
    if claim_policy == "claim_pool" and assignee.lower() in CLAIM_POOL_EMPTY:
        return True
    if assignee == agent:
        return True
    if not assignee or not agent:
        return False
    if assignee.lower() == agent.lower() or agent.lower() in assignee.lower():
        return True
    detected = detect_agent_id(config, assignee)
    return detected == agent


def is_available_task(
    root: Path,
    summary: dict[str, Any],
    registry: TaskTypeRegistry,
    agent: str,
    claim_policy: str,
    config: dict[str, Any] | None = None,
) -> bool:
    config = config or load_config(root)
    valid_statuses = available_statuses(config) if summary.get("source") == "issue" else {"todo"}
    if summary["status"] not in valid_statuses:
        return False
    if not dependencies_satisfied(root, registry, summary["dependencies"], config):
        return False
    return assignee_matches(config, summary.get("assignee", ""), agent, claim_policy)


def find_similar_tasks(
    root: Path,
    registry: TaskTypeRegistry,
    topic: str,
    task_type: str = "",
    threshold: float = 0.45,
    limit: int | None = None,
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    config = config or load_config(root)
    query = f"{task_type} {topic}".strip()
    matches = []
    threshold = 0.0 if not topic.strip() else threshold
    for summary in iter_project_tasks(root, registry, config):
        score = max(
            similarity(query, summary["searchable"], registry),
            similarity(topic, summary["title"], registry),
            similarity(topic, summary["slug"], registry),
        )
        if score >= threshold:
            summary["score"] = score
            matches.append(summary)
    matches.sort(key=lambda item: item["score"], reverse=True)
    return matches[:limit] if limit else matches


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")
