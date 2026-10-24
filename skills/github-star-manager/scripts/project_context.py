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
    ("transition", "转场"),
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

CAPABILITY_ALIASES = {
    "subtitle": ("subtitle", "caption", "字幕"),
    "timeline": ("timeline", "时间轴"),
    "render": ("render", "rendering", "渲染"),
    "animation": ("animation", "motion", "动画", "动效"),
    "transition": ("transition", "转场"),
    "audio": ("audio", "音频", "声音"),
    "voice": ("voice", "tts", "配音", "语音合成"),
    "asr": ("asr", "transcription", "转录"),
    "avatar": ("avatar", "character", "角色", "形象", "数字人"),
    "lipsync": ("lipsync", "lip-sync", "口型"),
    "cover": ("cover", "thumbnail", "封面", "缩略图"),
    "layout": ("layout", "typography", "排版"),
    "image": ("image", "图片", "图像"),
    "video": ("video", "视频", "成片"),
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


def implementation_files(profile: dict) -> list[Path]:
    """Bounded implementation references: entry code, scripts, and local tests."""
    root = Path(profile.get("skill_path") or "")
    if not root.is_dir():
        return []
    included = []
    for pattern in ("*.py", "scripts/*.py", "references/*.md", "tests/*.py"):
        for path in sorted(root.glob(pattern)):
            if path.is_file() and path.name not in {"SKILL.md", "TASKS.md"}:
                included.append(path)
    return included[:40]


def read_excerpt(path: Path, limit: int = 12_000) -> tuple[str, bool]:
    """Read a bounded excerpt for semantic evidence, with truncation visible."""
    raw = path.read_bytes()[:limit + 1]
    return raw[:limit].decode("utf-8", "replace"), len(raw) > limit


def implementation_excerpts(profile: dict, limit: int = 2_500) -> list[tuple[str, str, bool]]:
    """Read a few bounded excerpts; names remain anchors for Agent inspection."""
    result = []
    for path in implementation_files(profile)[:3]:
        try:
            text, truncated = read_excerpt(path, limit)
            result.append((str(path), text, truncated))
        except OSError:
            profile.setdefault("warnings", []).append(
                f"Implementation excerpt unavailable: {path.name}")
    return result


def capability_slug(text: str) -> str:
    """A deterministic, file-safe direction slug for bounded upstream hints."""
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", text.lower()).strip("-")
    return value[:48] or "capability"


def capability_hints(readme_text="", release=None, commits=(), readme_blob_sha=None) -> list[dict]:
    """Extract added-capability lines with immutable upstream anchors.

    Commit subjects intentionally do not create capability directions: they are
    evidence of recent change, while noisy history must not widen recall.
    """
    hints = []
    release = release or {}
    anchor = release.get("tag") or release.get("url") or release.get("published_at")
    if anchor:
        body = str(release.get("body") or "")
        lines = [line.strip(" \t-*#>`)(") for line in body.splitlines()]
        selected = [line for line in lines
                    if line and re.search(r"added|新增|支持|support|now provides|新增支持", line,
                                          re.I)]
        for text in selected[:30]:
            concepts = sorted({key for key, aliases in CAPABILITY_ALIASES.items()
                               if any(a.lower() in text.lower() for a in aliases)})
            if not concepts:
                continue
            for identity in concepts:
                hints.append({
                    "capability_key": capability_slug(identity),
                    "capability_label": identity,
                    "concepts": [identity],
                    "source": "release", "anchor": anchor, "text": text[:500],
                })
    # A README capability line is anchored by its blob SHA. Without that
    # anchor it cannot be identity-stable and must not become a direction.
    blob_sha = readme_blob_sha
    if isinstance(readme_text, str) and blob_sha:
        lines = [line.strip(" \t-*#>`)(") for line in readme_text.splitlines()]
        for text in [line for line in lines if line and re.search(
                r"features|功能|支持|provides|supports", line, re.I)][:30]:
            concepts = sorted({key for key, aliases in CAPABILITY_ALIASES.items()
                               if any(a.lower() in text.lower() for a in aliases)})
            if concepts:
                for identity in concepts:
                    hints.append({
                        "capability_key": capability_slug(identity),
                        "capability_label": identity, "concepts": [identity],
                        "source": "readme", "anchor": blob_sha, "text": text[:500],
                    })
    return hints


def positive_scope(text: str) -> str:
    return re.split("|".join(re.escape(marker) for marker in EXCLUSION_MARKERS),
                    text, maxsplit=1, flags=re.I)[0]


# The markers that open an exclusion. "不代替" and "不替代" state the same
# boundary as "不用于" and were missing, which left real exclusions
# unreadable.
EXCLUSION_MARKERS = ("不要用于", "不承担", "不用于", "不代替", "不替代",
                     "do not use", "not for")

# A marker only opens an exclusion. The exclusion itself is the short clause
# that follows it, up to the next sentence boundary. Cutting the text at the
# marker and keeping the whole remainder swallowed the rest of the document -
# including the skill's own positive vocabulary - and turned unrelated
# upstream repositories into false scope conflicts.
# A clause ends at a sentence boundary, a line break, or the closing quote of
# the quoted statement it belongs to. A comma does not end it: the real
# exclusions list their items with "、" or "，".
EXCLUSION_CLAUSE_END = re.compile(r"[。；;！!？?\n」』”\"]")
EXCLUSION_CLAUSE_MAX = 200

# Sentences that state a boundary without excluding a capability. They are
# routing or authorship statements, not negative scope.
NON_EXCLUSION_PATTERNS = (
    re.compile(r"由\s*\S+\s*(统一)?(管理|维护|负责)"),
    re.compile(r"走\s*\S+"),
    re.compile(r"通用创作方法"),
    re.compile(r"只(维护|负责|用于|支持|适配)"),
)

# A component can also limit itself with an explicit "only" clause instead of
# a negative marker. These are read from the description, which is the
# component's own statement of its boundary.
SCOPE_LIMIT_MARKER = re.compile(
    r"(?:本\s*(?:Skill|技能|工具|组件)?\s*)?只(?:维护|负责|支持|用于|适配|覆盖|处理|产出|生成)"
    r"(?:[^，。；;\n]{1,60})")

SCOPE_STATUS_CONFLICT = "conflicts_with_stated_scope"
SCOPE_STATUS_NONE = "no_stated_scope_conflict"
SCOPE_STATUS_UNPARSED = "stated_scope_unparsed"


def exclusion_clauses(text: str) -> list[str]:
    """Extract the stated exclusion clauses of a skill.

    Only the clause that follows an exclusion marker is returned, and only up
    to the first sentence boundary. The remainder of the document is never
    part of the result.
    """
    clauses = []
    for marker in EXCLUSION_MARKERS:
        for match in re.finditer(re.escape(marker), text, re.I):
            tail = text[match.end():]
            clause = EXCLUSION_CLAUSE_END.split(tail, maxsplit=1)[0].strip()
            clause = clause.strip(" \t\u3000,，、:：;；.。!！?？")
            if not clause:
                continue
            if len(clause) > EXCLUSION_CLAUSE_MAX:
                clause = clause[:EXCLUSION_CLAUSE_MAX]
            if any(pattern.search(clause) for pattern in NON_EXCLUSION_PATTERNS):
                continue
            clauses.append(clause)
    # Keep the first occurrence of each clause; a repeated marker is not a
    # second, different exclusion.
    seen, result = set(), []
    for clause in clauses:
        if clause in seen:
            continue
        seen.add(clause)
        result.append(clause)
    return result


def scope_limit_clauses(text: str) -> list[str]:
    """Read an explicit "only ..." boundary from a component's own text.

    Some components state their boundary with an explicit limit ("only
    maintains the card-scenario adaptation") instead of a negative marker.
    These clauses are read from the description only, and the extracted
    clause is the one the sentence itself states.
    """
    clauses = []
    for match in SCOPE_LIMIT_MARKER.finditer(text or ""):
        clause = match.group(0).strip()
        if clause and clause not in clauses:
            clauses.append(clause)
    return clauses


def exclusion_fragments(text: str) -> list[str]:
    """Return the stated negative scope of a skill, kept verbatim for review.

    The result is the short exclusion clause only. The historical behaviour
    returned everything after the marker up to the end of the text, which
    mixed a real exclusion with the whole document.
    """
    return exclusion_clauses(text)


def declared_exclusion_clauses(directory: Path):
    """Read an explicit exclusion declaration from the component itself.

    A component may state its boundary in a machine-readable way so the
    offline extractor does not have to guess. Two forms are accepted:

    - ``scope.json`` in the component directory with an ``exclusions`` list.
    - A ``declared_exclusions:`` line in ``TASKS.md`` followed by one
      clause per line.

    ``None`` means "no explicit declaration", which is different from an
    explicit empty list ("this component excludes nothing").
    """
    path = directory / "scope.json"
    if path.is_file():
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if isinstance(value, dict) and isinstance(value.get("exclusions"), list):
            clauses = [str(item).strip() for item in value["exclusions"]
                       if isinstance(item, str) and item.strip()]
            return clauses
        return None
    tasks = directory / "TASKS.md"
    if tasks.is_file():
        try:
            text = tasks.read_text(encoding="utf-8")
        except OSError:
            return None
        match = re.search(r"^declared_exclusions:[ \t]*$", text, re.M)
        if not match:
            return None
        clauses = []
        lines = text[match.end():].splitlines()
        # The declaration line is followed by its own items; a blank line
        # ends the declaration.
        while lines and not lines[0].strip():
            lines.pop(0)
        for line in lines:
            if not line.strip():
                break
            item = line.strip().lstrip("-*").strip()
            if not item:
                break
            clauses.append(item)
        return clauses
    return None


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
    """Match a local skill's stated exclusions against the upstream domain concepts.

    Only the skill's structured exclusion clauses take part. A concept that
    merely appears somewhere in the skill's own documentation is not a
    statement of negative scope and must not create a conflict.
    """
    vocabulary = {alias for aliases in CONCEPTS for alias in aliases}
    relevant = set(upstream_concepts) & vocabulary
    conflicts = []
    for fragment in profile.get("exclusion_clauses") or profile.get("exclusions") or []:
        hits = concept_hits(fragment, relevant)
        if hits:
            conflicts.append({"exclusion": fragment[:300], "conflicting_concepts": hits})
    return conflicts


def scope_status(profile: dict, conflicts) -> str:
    """The scope judgement of a profile, including the unparsed case.

    ``stated_scope_unparsed`` means the skill states no exclusion clause this
    tool could read. It is not the same as "no conflict": the scope is
    unverified and needs a human read.
    """
    if conflicts:
        return SCOPE_STATUS_CONFLICT
    if not (profile.get("exclusion_clauses") or profile.get("exclusions")):
        return SCOPE_STATUS_UNPARSED
    return SCOPE_STATUS_NONE


def scope_note(profile: dict) -> str | None:
    """Why the scope judgement could not be made, when it could not be made."""
    if profile.get("exclusion_clauses") or profile.get("exclusions"):
        return None
    return ("排除条款未能结构化解析，请人工确认：该组件没有可读取的排除短句，"
            "本次未做范围冲突判定")


def compare_snapshot_commit(pinned, head):
    if not pinned or not head:
        return "unknown"
    if len(pinned) < 40:
        return "same-prefix" if head.startswith(pinned) else "different-prefix"
    return "same" if pinned == head else "different"


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
                # An explicit limit is a stated boundary too. It is read from
                # the description only, and it never widens the exclusion.
                exclusions += scope_limit_clauses(meta["description"])
                declared = declared_exclusion_clauses(real)
                if declared is not None:
                    # An explicit declaration is authoritative. It replaces
                    # what the extractor read, so a component can state a
                    # boundary the parser cannot see.
                    exclusions = declared
                    local_warnings.append(
                        "Exclusion clauses taken from the component's explicit declaration")
                profile = {
                    "project_id": meta["name"], "name": meta["name"],
                    "skill_path": str(real), "origin": "dynamic-skill-scan/2",
                    "description": meta["description"], "needs": [t["text"] for t in tasks],
                    "capabilities": [meta["description"]], "tasks": tasks,
                    "exclusions": exclusions,
                    "exclusion_clauses": exclusions,
                    "exclusion_source": "declared" if declared is not None else "extracted",
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
        # Current implementation excerpts can supply real capabilities that a
        # short description omits. They are bounded and never treated as a need
        # when their concept is explicitly excluded.
        implementation_rows = implementation_excerpts({
            "skill_path": profile["skill_path"], "warnings": profile["warnings"]})
        implementation_text = [text for _path, text, _truncated in implementation_rows]
        profile["implementation_excerpt_refs"] = [
            {**{"path": path}, **({"truncated": True} if truncated else {})}
            for path, _text, truncated in implementation_rows]
        description = positive_scope(profile["description"])
        text = " ".join([profile["name"], description, *profile["needs"], *implementation_text])
        positive = terms_for(text)
        # A statement of exclusion is not a need. Remove excluded concepts from
        # positive recall while preserving them as inspectable scope warnings.
        excluded = set()
        for fragment in profile["exclusions"]:
            # Match aliases with word boundaries, then exclude the whole
            # canonical concept. A substring such as "academic" containing
            # "cad" must not erase CAD capabilities; conversely, "不承担配音"
            # must remove voice/tts/配音 as one concept, not just one spelling.
            for aliases in CONCEPTS:
                if concept_hits(fragment, aliases):
                    excluded.update(aliases)
        # Keep only whole aliases present in positive recall. This avoids
        # expanding a concept merely because its synonym appeared in a negative
        # fragment.
        positive_concepts = set(positive)
        # A concept asserted positively is a real capability even if a later
        # exclusion narrows one use case ("voice clips, not voice courses").
        asserted = set()
        for aliases in CONCEPTS:
            if positive_concepts.intersection(aliases):
                asserted.update(aliases)
        excluded = {alias for alias in excluded if alias not in asserted}
        profile["search_terms"] = sorted(positive - excluded)
        profile["primary_terms"] = sorted(terms_for(profile["name"] + " " + description))
        profile["implementation_terms"] = sorted(terms_for(" ".join(implementation_text)) - excluded)
        if implementation_rows and not profile["implementation_terms"]:
            profile["warnings"].append(
                "Implementation excerpts yielded no recognized capability concepts")
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
