"""Bounded discovery of current local skills; no project registration required."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

MAX_DOCUMENT_BYTES = 256_000
IGNORED = {"archive", ".system", "node_modules", "test", "output", ".git"}
CONCEPTS = (
    ("video", "视频", "成片"), ("animation", "motion", "动画", "动效"),
    ("subtitle", "caption", "字幕"), ("timeline", "时间轴"),
    ("render", "rendering", "渲染"), ("audio", "音频", "声音"),
    ("voice", "tts", "配音", "语音合成"), ("asr", "transcription", "转录"),
    ("avatar", "character", "角色", "形象", "数字人"),
    ("lipsync", "lip-sync", "口型"), ("sprite", "精灵"),
    ("cover", "thumbnail", "封面", "缩略图"), ("layout", "typography", "排版"),
    ("illustration", "插画", "插图"), ("image", "图片", "图像"),
    ("ocr", "文字识别"), ("pdf",), ("cad", "3d", "建模"),
    ("patent", "专利"), ("trademark", "商标"), ("contract", "合同"),
    ("legal", "法律"), ("browser", "浏览器"), ("memory", "记忆"),
    ("spreadsheet", "excel", "表格"), ("slides", "presentation", "幻灯片"),
    ("search", "retrieval", "检索"), ("workflow", "automation", "自动化"),
)
STOP = {
    "the", "and", "with", "for", "from", "when", "this", "that", "use", "using",
    "skill", "skills", "agent", "agents", "python", "tool", "tools", "支持", "使用",
    "用户", "用于", "需要", "项目", "目标", "输出", "输入", "功能", "能力",
    "任务", "文件", "流程", "提供", "已有", "是否", "当前", "本轮",
    "claude", "codex", "code", "open", "source", "text", "read", "run", "task",
    "app", "cli", "install", "plugin", "integration", "windows", "desktop",
    "github", "model", "models", "context", "support", "supports", "based",
}


def digest(value) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def read_document(path: Path) -> tuple[str, str, bool]:
    # Hash the entire bounded document. Oversized documents stay visible but
    # are not used to assert a complete target fingerprint.
    with path.open("rb") as stream:
        raw = stream.read(MAX_DOCUMENT_BYTES + 1)
    if len(raw) > MAX_DOCUMENT_BYTES:
        return raw[:MAX_DOCUMENT_BYTES].decode("utf-8", "replace"), "", True
    return raw.decode("utf-8"), hashlib.sha256(raw).hexdigest(), False


def frontmatter(text: str) -> dict:
    """Read the scalar name/description subset, including YAML block strings."""
    lines = text.lstrip("\ufeff").splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("missing frontmatter")
    end = next((i for i, line in enumerate(lines[1:], 1) if line.strip() == "---"), None)
    if end is None:
        raise ValueError("unterminated frontmatter")
    fields = {}
    i = 1
    while i < end:
        match = re.match(r"^([a-z_]+):\s*(.*)$", lines[i])
        if not match:
            i += 1
            continue
        key, value = match.groups()
        i += 1
        if value in ("|", ">", "|-", ">-", "|+", ">+") or not value:
            block = []
            while i < end and (not lines[i].strip() or lines[i].startswith((" ", "\t"))):
                block.append(lines[i].strip())
                i += 1
            value = " ".join(block)
        elif value.startswith('"') and value.endswith('"'):
            value = json.loads(value)
        elif value.startswith("'") and value.endswith("'"):
            value = value[1:-1].replace("''", "'")
        fields[key] = value
    if not fields.get("name") or not fields.get("description"):
        raise ValueError("missing name/description")
    return fields


def active_task_excerpt(text: str) -> list[dict]:
    """Only select explicit current signals; retain line refs for Agent review."""
    result, skipped_level = [], None
    for number, line in enumerate(text.splitlines(), 1):
        heading = re.match(r"^(#{1,6})\s+(.*)", line)
        if heading:
            level, title = len(heading[1]), heading[2]
            if skipped_level is not None and level <= skipped_level:
                skipped_level = None
            if re.search(r"历史|归档|已完成|\bDONE\b|\bCLOSED\b", title, re.I):
                skipped_level = level
        if skipped_level is not None or re.search(r"\[x\]|\bDONE\b|\bCLOSED\b", line, re.I):
            continue
        if re.search(r"\[\s\]|\bREADY\b|\bIN_PROGRESS\b|(?:^[-* ]+)(?:目标|缺口|需求)[：:]", line):
            result.append({"line": number, "text": line.strip()[:500]})
        if len(result) >= 24:
            break
    return result


def default_roots() -> list[Path]:
    roots = [Path(__file__).resolve().parents[2]]
    codex_root = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    roots += [codex_root / "skills", Path.home() / ".agents" / "skills"]
    return list(dict.fromkeys(p.resolve() for p in roots if p.is_dir()))


def git_root(path: Path):
    for parent in [path, *path.parents]:
        if (parent / ".git").exists():
            return parent
    return None


def collect_activity(profiles: list[dict], days: int = 30):
    groups = defaultdict(list)
    for profile in profiles:
        root = git_root(Path(profile["skill_path"]))
        if root:
            groups[root].append(profile)
    for root, members in groups.items():
        paths = [str(Path(p["skill_path"]).relative_to(root)) for p in members]
        try:
            proc = subprocess.run(
                ["git", "-c", "core.quotePath=false", "-c", "core.fsmonitor=false",
                 "-C", str(root), "log", "--max-count=2000",
                 "--format=@@%H|%cI", "--name-only", "--", *paths],
                capture_output=True, text=True, timeout=20,
                env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"}, check=False)
            if proc.returncode:
                raise ValueError("git log failed")
            commits = defaultdict(dict)
            oid, date = None, None
            for line in proc.stdout.splitlines():
                if line.startswith("@@"):
                    oid, date = line[2:].split("|", 1)
                elif line and oid:
                    for relative in paths:
                        if relative == "." or line.startswith(relative + "/"):
                            commits[relative][oid] = date
            for profile, relative in zip(members, paths):
                entries = commits[relative]
                cutoff = datetime.now(timezone.utc) - timedelta(days=days)
                recent = sum(datetime.fromisoformat(date) >= cutoff for date in entries.values())
                profile["activity"] = {
                    "status": "observed", "window_days": days, "commits": recent,
                    "latest_at": max(entries.values(), default=None),
                    "latest_commit": next(iter(entries), None),
                    "scope": relative, "history_bounded": True,
                }
        except (OSError, ValueError, subprocess.TimeoutExpired):
            for profile in members:
                profile["activity"]["status"] = "unavailable"
                profile["warnings"].append("Git activity unavailable; not treated as inactivity")


def terms_for(text: str) -> set[str]:
    lower = text.lower()
    terms = set(re.findall(r"[a-z][a-z0-9+#.]{2,}", lower)) - STOP
    for aliases in CONCEPTS:
        if any((a in lower if re.search(r"[\u4e00-\u9fff]", a)
                else re.search(r"(?<![a-z0-9])" + re.escape(a) + r"(?![a-z0-9])", lower))
               for a in aliases):
            terms.update(aliases)
    return terms - STOP


def positive_scope(text: str) -> str:
    return re.split(r"不要用于|不承担|不用于|do not use|not for", text, maxsplit=1, flags=re.I)[0]


EXCLUSION_MARKERS = ("不要用于", "不承担", "不用于", "do not use", "not for")


def exclusion_fragments(text: str) -> list[str]:
    """Return the stated negative scope of a skill, kept verbatim for review."""
    parts = re.split("|".join(re.escape(marker) for marker in EXCLUSION_MARKERS),
                     text, flags=re.I)
    return [part.strip() for part in parts[1:] if part.strip()]


def concept_hits(text: str, concepts) -> list[str]:
    """Which concept aliases appear in a fragment."""
    hits = []
    for concept in concepts:
        if not isinstance(concept, str) or not concept:
            continue
        if re.search(r"[\u4e00-\u9fff]", concept):
            if concept.lower() in text.lower():
                hits.append(concept)
        elif re.search(r"(?<![a-z0-9])" + re.escape(concept.lower()) + r"(?![a-z0-9])",
                       text.lower()):
            hits.append(concept)
    return sorted(set(hits))


def scope_conflicts(profile: dict, upstream_concepts) -> list[dict]:
    """Match a local skill's stated exclusions against the upstream domain concepts."""
    conflicts = []
    for fragment in profile.get("exclusions") or []:
        hits = concept_hits(fragment, upstream_concepts)
        if hits:
            conflicts.append({"exclusion": fragment[:300], "conflicting_concepts": hits})
    return conflicts


def shared_repo_revision(repo: dict) -> str:
    """Metadata-level revision shared by every discovery and watch channel."""
    raw = json.dumps({
        "id": repo.get("id") or repo.get("full_name"),
        "pushed_at": repo.get("pushed_at"),
        "description": repo.get("description"),
        "topics": repo.get("topics"),
    }, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def shared_evidence_revision(record: dict) -> str:
    """Upstream content-level revision shared by every discovery and watch channel."""
    record = record or {}
    raw = json.dumps({
        "head": record.get("head_sha"),
        "release": record.get("release"),
        "readme": (record.get("readme") or {}).get("blob_sha"),
    }, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def discover(roots=None, project=None) -> tuple[list[dict], list[str]]:
    roots = [Path(r).expanduser().resolve() for r in (roots or default_roots())]
    profiles, warnings, seen = [], [], set()
    for root in roots:
        if not root.is_dir():
            warnings.append(f"Skill root unavailable: {root}")
            continue
        # Only direct skill children (or a directly supplied skill), never archives.
        directories = [root] if (root / "SKILL.md").is_file() else sorted(root.iterdir())
        for directory in directories:
            if directory.name in IGNORED or directory.name.startswith("."):
                continue
            real = directory.resolve()
            if real in seen or not (real / "SKILL.md").is_file():
                continue
            seen.add(real)
            try:
                text, sha, truncated = read_document(real / "SKILL.md")
                meta = frontmatter(text)
                if project and project.split("@", 1)[0] not in (meta["name"], directory.name, str(real)):
                    continue
                refs = {str(real / "SKILL.md"): sha} if sha else {}
                tasks, local_warnings = [], []
                if truncated:
                    local_warnings.append("SKILL.md exceeds read budget; target incomplete")
                if (real / "TASKS.md").is_file():
                    task_text, task_sha, limited = read_document(real / "TASKS.md")
                    tasks = active_task_excerpt(task_text)
                    if task_sha:
                        refs[str(real / "TASKS.md")] = task_sha
                    if limited:
                        local_warnings.append("TASKS.md exceeds read budget; target incomplete")
                exclusions = exclusion_fragments(meta["description"])
                exclusions += exclusion_fragments("\n".join(t["text"] for t in tasks))
                profile = {
                    "project_id": meta["name"], "name": meta["name"],
                    "skill_path": str(real), "origin": "dynamic-skill-scan/2",
                    "description": meta["description"], "needs": [t["text"] for t in tasks],
                    "capabilities": [meta["description"]], "tasks": tasks,
                    "exclusions": exclusions,
                    "source_ref": list(refs), "hashes": refs, "warnings": local_warnings,
                    "activity": {"status": "not_git", "commits": 0, "latest_at": None,
                                 "latest_commit": None},
                }
                profiles.append(profile)
            except (OSError, UnicodeError, ValueError) as exc:
                warnings.append(f"Cannot read skill {directory.name}: {type(exc).__name__}")
    duplicates = defaultdict(list)
    for profile in profiles:
        duplicates[profile["name"]].append(profile)
    for group in duplicates.values():
        if len(group) > 1:
            for profile in group:
                profile["project_id"] += "@" + digest(profile["skill_path"])[:8]
            warnings.append("Duplicate skill names use a path-qualified project_id")
    if project and "@" in project:
        profiles = [p for p in profiles if p["project_id"] == project]
    collect_activity(profiles)
    for profile in profiles:
        profile["target_revision"] = digest({
            "files": {Path(p).name: h for p, h in profile["hashes"].items()},
            "implementation": profile["activity"].get("latest_commit"),
        })
        description = positive_scope(profile["description"])
        text = profile["name"] + " " + description + " " + " ".join(profile["needs"])
        profile["search_terms"] = sorted(terms_for(text))
        profile["primary_terms"] = sorted(terms_for(profile["name"] + " " + description))
    profiles.sort(key=lambda p: (-p["activity"]["commits"], p["project_id"]))
    return profiles, warnings


def match_terms(profile: dict, repo: dict) -> list[str]:
    target = set(profile.get("search_terms") or terms_for(
        " ".join(profile.get("needs", []) + profile.get("capabilities", []))))
    upstream = repo.get("_search_terms")
    if upstream is None:
        upstream = terms_for(" ".join([
        repo.get("full_name") or "", repo.get("description") or "",
        repo.get("description_zh") or "", " ".join(repo.get("topics") or []),
        ]))
    # Synonym expansion should not multiply a single concept into several votes.
    hits = target & upstream
    result = set(hits)
    for aliases in CONCEPTS:
        if hits.intersection(aliases):
            result.difference_update(aliases)
            result.add(aliases[0])
    return sorted(result)
