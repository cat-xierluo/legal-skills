#!/usr/bin/env python3
"""Public release gate for the magpie-optimizer Skill tree.

Purpose: scan the directory tree that is about to be published and report
private data, invalid sample/schema files, broken relative Markdown links,
uncovered local config files and version drift between SKILL.md and
CHANGELOG.md.

Read-only boundary: the script only reads files under the target root and
runs two read-only git plumbing commands (`rev-parse`, `ls-files`). It never
calls the Magpie CLI, never reads `~/.config/magpie`, never changes the local
gateway, and never issues a model request -- no quota is consumed. The only
write is the optional `--output` report file, created with mode 0600.

Reporting boundary: findings carry the relative file path, the line number, a
rule code and a short fix hint. Matched text (keys, e-mail addresses, private
path fragments) is never echoed back into the report.

Exit codes: 0 = pass, 1 = findings (fail, or any fail/warn with --strict),
2 = usage error or read failure.
"""
import sys

sys.dont_write_bytecode = True

import argparse
import datetime as dt
import fnmatch
import json
import os
import re
import subprocess
import urllib.parse
from pathlib import Path

SCHEMA = "magpie-public-release-check.v1"

# Extensions treated as reviewable text. Anything else (archives, images,
# bundles) is skipped instead of being scanned as noise.
TEXT_SUFFIXES = {
    ".md", ".json", ".py", ".sh", ".bash", ".zsh", ".ps1", ".bat", ".txt",
    ".yaml", ".yml", ".toml", ".cfg", ".ini", ".conf", ".properties", ".env",
    ".xml", ".html", ".rst", ".csv", ".js", ".mjs", ".cjs", ".ts", ".tsx",
    ".jsx", ".go", ".rs", ".rb", ".java", ".kt", ".swift", ".sql", ".svg",
}
# Extension-less files (Makefile, LICENSE, .gitignore, ...) are small text.
NO_SUFFIX_MAX_BYTES = 65536
MAX_TEXT_BYTES = 2 * 1024 * 1024
BINARY_SNIFF_BYTES = 8192


class Refused(Exception):
    pass


def require(ok, reason):
    if not ok:
        raise Refused(reason)


def _drop_cached_bytecode():
    """Remove this module's own cached bytecode.

    `sys.dont_write_bytecode` keeps later imports from writing caches, but the
    import system writes the cache of the imported module itself before this
    body runs. Dropping it keeps the tree free of __pycache__ artefacts.
    """
    try:
        source = Path(__file__).resolve()
        cached = source.parent / "__pycache__"
        if not cached.is_dir():
            return
        for item in cached.glob(source.stem + ".*.pyc"):
            item.unlink()
        if not any(cached.iterdir()):
            cached.rmdir()
    except OSError:
        pass


_drop_cached_bytecode()


# --------------------------------------------------------------------------
# Pure detectors. These are the public contract: tests import them directly.
# --------------------------------------------------------------------------

# Placeholder markers that make an assignment harmless in a sample file.
PLACEHOLDER_WORDS = (
    "example", "your", "placeholder", "xxx", "changeme", "todo", "redacted",
    "dummy", "sample", "notreal", "fake",
)


def is_explicit_placeholder(value):
    """Only the documented placeholder markers (words, <>, mask characters)."""
    text = str(value).strip().strip('"').strip("'").strip()
    if not text:
        return True
    low = text.lower()
    if any(word in low for word in PLACEHOLDER_WORDS):
        return True
    if "<" in text or ">" in text:
        return True
    if re.fullmatch(r"[*x•…]+", text):
        return True
    return False


def is_placeholder_value(value):
    """Heuristic: does an assigned value look like a documented placeholder?"""
    text = str(value).strip().strip('"').strip("'").strip()
    if not text:
        return True
    if is_explicit_placeholder(text):
        return True
    # Lower-case letters/digits/hyphens only and short: generic filler.
    if re.fullmatch(r"[a-z0-9\-_]+", text) and len(text) < 12:
        return True
    return False


def _assignment_value_pattern():
    return r"(?P<value>\"[^\"\n]*\"|'[^'\n]*'|[^\s,;)\]}]+)"


SECRET_RULES = (
    # OpenAI-style key: sk- plus at least six alphanumerics. The lookbehind
    # keeps identifiers such as "task-before-1" out of the result set.
    ("sk_prefix", re.compile(r"(?<![A-Za-z0-9_])sk-[A-Za-z0-9]{6,}")),
    ("api_key_assignment",
     re.compile(r"(?i)(?<![A-Za-z0-9_])api[_-]?key(?![A-Za-z0-9_])\s*[:=]\s*"
                + _assignment_value_pattern())),
    ("bearer_token",
     re.compile(r"(?i)(?<![A-Za-z0-9_])bearer\s+(?P<value>[A-Za-z0-9._~+/=-]{6,})")),
    ("credential_assignment",
     re.compile(r"(?i)(?<![A-Za-z0-9_])(?:password|passwd|secret|cookie|authorization)"
                r"(?![A-Za-z0-9_])\s*[:=]\s*" + _assignment_value_pattern())),
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
)

# Rules whose matched value may legitimately be a documented placeholder.
PLACEHOLDER_EXEMPT_RULES = {
    "api_key_assignment", "bearer_token", "credential_assignment",
}
# Auth scheme keywords carry no secret material on their own; the secret in
# 'Authorization: Bearer <token>' is the token behind the scheme.
AUTH_SCHEMES = {"bearer", "basic", "digest", "token", "negotiate", "oauth"}


def effective_value(value):
    """Strip quotes and a leading auth scheme keyword from an assigned value."""
    text = str(value).strip().strip('"').strip("'").strip()
    parts = text.split(None, 1)
    if parts and parts[0].lower() in AUTH_SCHEMES:
        return parts[1].strip() if len(parts) > 1 else ""
    return text


def find_secret_matches(text):
    """Return [(line_no, rule_code)] for credential-shaped hits.

    Line numbers start at 1. The matched text is deliberately not returned so
    it can never leak into a report.
    """
    return _find_secret_matches(text, is_placeholder_value)


def _find_secret_matches(text, placeholder_check):
    """Shared matcher; `placeholder_check` decides what counts as harmless."""
    hits = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for rule, pattern in SECRET_RULES:
            for match in pattern.finditer(line):
                if rule in PLACEHOLDER_EXEMPT_RULES:
                    value = match.groupdict().get("value")
                    if value is not None:
                        effective = effective_value(value)
                        if rule == "bearer_token":
                            if is_explicit_placeholder(effective):
                                continue
                        elif placeholder_check(effective):
                            continue
                hits.append((line_no, rule))
                break
    return hits


EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+\-])[A-Za-z0-9._%*+\-]+@[A-Za-z0-9.\-*]+\.[A-Za-z]{2,}"
)
EXCLUDED_EMAIL_DOMAINS = {
    "example.com", "example.org", "example.net", "example.invalid",
}
EXCLUDED_EMAIL_TLDS = {"invalid", "localhost", "example", "local"}


def _is_real_email_domain(domain):
    domain = domain.lower().strip(".")
    if not domain or "." not in domain:
        return False
    if domain in EXCLUDED_EMAIL_DOMAINS:
        return False
    tld = domain.rsplit(".", 1)[-1]
    if tld in EXCLUDED_EMAIL_TLDS:
        return False
    if domain.endswith(".invalid") or domain.endswith(".localhost"):
        return False
    if not re.fullmatch(r"[a-z]{2,24}", tld):
        return False
    return True


def find_personal_emails(text):
    """Return [(line_no, email)] for complete, non-placeholder addresses.

    example.com / example.org / example.net / example.invalid / *.invalid /
    localhost are accepted, and masked forms containing '*' are not reported.
    The address itself is returned for internal decisions only.
    """
    hits = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for match in EMAIL_RE.finditer(line):
            address = match.group(0)
            if "*" in address:
                continue
            local, _, domain = address.rpartition("@")
            if not local or not _is_real_email_domain(domain):
                continue
            hits.append((line_no, address))
    return hits


HOME_PATH_RE = re.compile(r"/Users/[A-Za-z0-9._\-]+")


def find_home_paths(text):
    """Return [(line_no, path)] for local absolute paths under /Users/<name>/."""
    hits = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for match in HOME_PATH_RE.finditer(line):
            hits.append((line_no, match.group(0)))
    return hits


def markdown_link_spans(text):
    """Return [(line_no, target)] for every Markdown link in the text."""
    spans = []
    for match in re.finditer(r"\]\(([^)\n]*)\)", text):
        raw = match.group(1).strip()
        if not raw:
            continue
        token = raw.split()[0].strip()
        if token.startswith("<") and token.endswith(">"):
            token = token[1:-1]
        if not token:
            continue
        line_no = text.count("\n", 0, match.start()) + 1
        spans.append((line_no, token))
    return spans


def _is_external_link(target):
    if target.startswith("#"):
        return True
    if target.startswith(("http://", "https://", "mailto:", "tel:", "ftp://")):
        return True
    if re.match(r"^[A-Za-z][A-Za-z0-9+.\-]*:", target):
        return True
    if target.startswith("/") or target.startswith("~"):
        return True
    return False


def markdown_links(text):
    """Return relative link targets in order of first appearance, deduplicated.

    http://, https://, mailto: and '#' anchors are skipped.
    """
    targets = []
    for _line_no, target in markdown_link_spans(text):
        if _is_external_link(target):
            continue
        if target not in targets:
            targets.append(target)
    return targets


def _translate_pattern(pattern):
    """Translate one gitignore glob into a regular expression body."""
    out = []
    index = 0
    length = len(pattern)
    while index < length:
        char = pattern[index]
        if char == "*":
            if pattern[index:index + 3] == "**/":
                out.append("(?:.*/)?")
                index += 3
                continue
            if pattern[index:index + 2] == "**":
                out.append(".*")
                index += 2
                continue
            out.append("[^/]*")
            index += 1
            continue
        if char == "?":
            out.append("[^/]")
            index += 1
            continue
        if char == "[":
            end = index + 1
            if end < length and pattern[end] in "!^":
                end += 1
            if end < length and pattern[end] == "]":
                end += 1
            while end < length and pattern[end] != "]":
                end += 1
            if end >= length:
                out.append(re.escape(char))
                index += 1
                continue
            body = pattern[index + 1:end]
            if body.startswith("!"):
                body = "^" + body[1:]
            out.append("[" + body + "]")
            index = end + 1
            continue
        out.append(re.escape(char))
        index += 1
    return "".join(out)


def _match_pattern(pattern, target, anchored=False):
    """Does one gitignore pattern match the given path?

    A pattern without a slash is matched against the last path segment
    (Git matches such a pattern at any depth); a pattern with a slash is
    relative to the directory that owns the .gitignore file and is matched
    against the whole relative path.  A leading slash anchors the pattern
    to the top level of that directory.
    """
    if not pattern or not target:
        return False
    if anchored and "**" not in pattern:
        # An anchored pattern names the first segments of the path.
        depth = len(pattern.split("/"))
        subject = "/".join(target.split("/")[:depth])
    elif "/" in pattern:
        subject = target
    else:
        subject = target.rsplit("/", 1)[-1]
    try:
        regex = re.compile("(?s:" + _translate_pattern(pattern) + r")\Z")
    except re.error:
        return False
    return bool(regex.match(subject))


def _ancestor_prefixes(path):
    """The path prefixes of a path, excluding the path itself.

    For "a/b/c" the prefixes are "a" and "a/b"; the bare segment names
    are not prefixes and must not be matched on their own.
    """
    segments = path.split("/")
    return ["/".join(segments[:index]) for index in range(1, len(segments))]


def _ignore_decision(rel_path, ignore_lines):
    """Decide one .gitignore file against one path.

    Returns "ignored", "not-ignored" or "none".  Git's ordering rules are
    reproduced: the last matching pattern decides, a directory rule excludes
    everything below it, and a file below an excluded directory cannot be
    re-included by a later negation (only the directory rule itself can be
    negated).
    """
    raw = str(rel_path or "").replace(os.sep, "/").strip()
    while raw.startswith("./"):
        raw = raw[2:]
    is_dir = raw.endswith("/")
    path = raw.strip("/")
    if not path:
        return "none"
    segments = path.split("/")
    ancestors = _ancestor_prefixes(path)
    file_state = "none"
    dir_state = {}
    for raw_line in ignore_lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        negated = line.startswith("!")
        if negated:
            line = line[1:].strip()
            if line.startswith("!"):
                line = line[1:].strip()
        if not line:
            continue
        dir_only = line.endswith("/")
        pattern = line.rstrip("/")
        anchored = pattern.startswith("/")
        if anchored:
            pattern = pattern[1:]
        if not pattern:
            continue
        matched = _match_pattern(pattern, path, anchored)
        if dir_only:
            if matched:
                dir_state[path] = not negated
            for ancestor in ancestors:
                if _match_pattern(pattern, ancestor, anchored):
                    dir_state[ancestor] = not negated
            continue
        if matched:
            file_state = "not-ignored" if negated else "ignored"
        for ancestor in ancestors:
            if _match_pattern(pattern, ancestor, anchored):
                dir_state[ancestor] = not negated
    for ancestor in ancestors:
        if dir_state.get(ancestor):
            return "ignored"
    if is_dir and dir_state.get(path):
        return "ignored"
    return file_state


def gitignore_covers(name, ignore_lines):
    """Does the given .gitignore content cover this file name or path?

    Supports the common spellings: '*.local.*', 'name', 'path/name', '*.json',
    'dir/' and '**/dir/name'. A later '!pattern' negates an earlier match.

    The rules follow Git's ordering: the last matching pattern decides. A
    directory rule ('dir/') covers everything below that directory, and a
    file below an excluded directory cannot be re-included by a later
    negation -- exactly like Git, which does not descend into an excluded
    directory. A negated directory rule re-includes the directory itself
    and leaves the files below it to the remaining rules.
    """
    return _ignore_decision(name, ignore_lines) == "ignored"


CHANGELOG_VERSION_RE = re.compile(r"^##\s*\[(\d+(?:\.\d+)+)\]", re.MULTILINE)


def latest_changelog_version(text):
    """Return the first '## [x.y.z]' version heading in the text, else None."""
    match = CHANGELOG_VERSION_RE.search(text)
    return match.group(1) if match else None


def skill_frontmatter_version(text):
    """Return SKILL.md frontmatter metadata.version, else None."""
    frontmatter = re.match(r"^---\s*\r?\n(.*?)\r?\n---\s*(?:\r?\n|$)", text, re.DOTALL)
    if not frontmatter:
        return None
    lines = frontmatter.group(1).splitlines()
    metadata_indent = None
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if metadata_indent is None:
            if re.match(r"^metadata\s*:", stripped):
                metadata_indent = indent
                continue
            # No metadata block at all: fall back to a top level version key.
            version = re.match(r"^version\s*:\s*(.+)$", stripped)
            if version:
                return version.group(1).strip().strip('"').strip("'") or None
            continue
        if indent <= metadata_indent:
            break
        version = re.match(r"^version\s*:\s*(.+)$", stripped)
        if version:
            return version.group(1).strip().strip('"').strip("'") or None
    return None


# --------------------------------------------------------------------------
# File manifest
# --------------------------------------------------------------------------

def _run_git(root, args):
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, text=True, timeout=60,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return None


def _git_check_ignore(root, rel_path):
    """Ask Git whether the path is ignored; True/False, or None if unknown.

    `git check-ignore --no-index` evaluates the ignore rules of the
    surrounding repository without consulting the index and without writing
    anything, so a tracked file is judged by its rules as well.
    """
    top = _worktree_root(root)
    if top is None:
        return None
    try:
        base = Path(root).resolve().relative_to(top)
        relative = (base / rel_path).as_posix()
    except ValueError:
        return None
    result = _run_git(top, ["check-ignore", "--no-index", "-q", "--", relative])
    if result is None:
        return None
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    return None


def is_git_work_tree(root):
    result = _run_git(root, ["rev-parse", "--is-inside-work-tree"])
    return result is not None and result.returncode == 0 and result.stdout.strip() == "true"


def _walk_paths(root):
    """Every file below root, except the .git directory itself."""
    paths = []
    for dirpath, dirnames, filenames in os.walk(root):
        symlinked_dirs = []
        for name in sorted(dirnames):
            if name == ".git":
                continue
            if _is_symlink(Path(dirpath) / name):
                # A symlinked directory may point outside the tree that is
                # about to be published: it is never descended into.
                symlinked_dirs.append(Path(dirpath) / name)
        dirnames[:] = sorted(d for d in dirnames
                            if d != ".git" and not _is_symlink(Path(dirpath) / d))
        for link in symlinked_dirs:
            paths.append(link.relative_to(root).as_posix())
        for name in sorted(filenames):
            full = Path(dirpath) / name
            if _is_symlink(full):
                # A symlink may point outside the tree that is about to be
                # published; its target is not read, but the link itself
                # still belongs to the published tree and is reported.
                paths.append(full.relative_to(root).as_posix())
                continue
            paths.append(full.relative_to(root).as_posix())
    return paths


def _is_symlink(path):
    try:
        return path.is_symlink()
    except OSError:
        return True


def _symlink_in_chain(root, rel_path):
    """Return the first path component that is a symlink, or None.

    The whole chain below root is checked, not only the leaf: a tracked
    file "a/file" is read through "a" when "a" has been replaced by a
    symlink, and that link may point outside the tree that is about to be
    published.  The chain is walked from the root downwards and the first
    link short-circuits the check, so no target is ever read.
    """
    current = root
    walked = []
    for segment in rel_path.split("/"):
        if not segment:
            continue
        current = current / segment
        walked.append(segment)
        if _is_symlink(current):
            return "/".join(walked[:-1]) if len(walked) > 1 else segment
    return None


def _is_text_file(path):
    try:
        size = path.stat().st_size
    except OSError:
        return False
    name = path.name
    if name == ".gitignore" or name == ".env" or name.startswith(".env."):
        return True
    suffix = path.suffix.lower()
    if suffix in TEXT_SUFFIXES:
        return True
    if suffix == "":
        return size <= NO_SUFFIX_MAX_BYTES
    return False


def _has_nul(path):
    try:
        with path.open("rb") as handle:
            return b"\x00" in handle.read(BINARY_SNIFF_BYTES)
    except OSError:
        return True


def _decode_text(path):
    """Return (text, problem) for a file; problem is None when it is clean."""
    try:
        data = path.read_bytes()
    except OSError:
        return None, "文件无法读取"
    if b"\x00" in data[:BINARY_SNIFF_BYTES]:
        return None, "文件含有 NUL 字节，不是可检查的文本"
    try:
        return data.decode("utf-8"), None
    except UnicodeDecodeError:
        return None, "文件不是合法的 UTF-8 文本"


def collect_manifest(root):
    """Return (text_files, all_paths, tracked_missing, unreadable, mode).

    In a git work tree the manifest is the set of tracked files; otherwise it
    is every file on disk minus .git and minus binary content.  ``all_paths``
    keeps every candidate path, including the ones whose content is not
    scanned, so that the private-layer rules do not depend on the file
    type.  ``unreadable`` collects every path whose content could not be
    checked: a symlink anywhere in its path chain, a file that is missing
    from the work tree, a file that is too large, a binary or NUL-bearing
    file and a file that is not valid UTF-8.  None of them is silently
    skipped.
    """
    mode = "git" if is_git_work_tree(root) else "walk"
    if mode == "git":
        result = _run_git(root, ["ls-files", "-z"])
        require(result is not None and result.returncode == 0, "git_ls_files_failed")
        raw_paths = [p for p in result.stdout.split("\0") if p]
    else:
        raw_paths = _walk_paths(root)
    seen = set()
    ordered = []
    for raw in raw_paths:
        rel = raw.replace(os.sep, "/")
        while rel.startswith("./"):
            rel = rel[2:]
        if not rel or rel in seen:
            continue
        seen.add(rel)
        ordered.append(rel)
    ordered.sort()
    manifest = []
    missing = []
    unreadable = []
    for rel in ordered:
        full = root / rel
        link = _symlink_in_chain(root, rel)
        if link is not None:
            # The target is never read (it may live outside the tree); the
            # link is reported so that a human decides what to publish.
            unreadable.append((rel, "路径上的 " + link + " 是符号链接，目标未读取"))
            continue
        if not full.is_file():
            missing.append(rel)
            continue
        try:
            size = full.stat().st_size
        except OSError:
            unreadable.append((rel, "文件无法读取"))
            continue
        if size > MAX_TEXT_BYTES:
            unreadable.append((rel, "文件超过可检查的大小上限"))
            continue
        if not _is_text_file(full):
            unreadable.append((rel, "文件类型不在可检查的文本范围内"))
            continue
        text, problem = _decode_text(full)
        if problem is not None:
            unreadable.append((rel, problem))
            continue
        manifest.append(rel)
    return manifest, ordered, missing, unreadable, mode


def read_text(path):
    data = path.read_bytes()
    return data.decode("utf-8", errors="replace")


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------

def _finding(code, severity, file, line, detail):
    return {"code": code, "severity": severity, "file": file,
            "line": int(line or 0), "detail": detail}


def check_text_content(rel_path, text):
    """Secret / e-mail / private-path findings for one text file."""
    findings = []
    base = rel_path.rsplit("/", 1)[-1]
    task_doc = base in ("TASKS.md", "DECISIONS.md")
    # Sample and schema files keep the documented placeholder exemption; in
    # every other file a non-empty assigned value is treated as a real secret.
    sample_doc = base.endswith(".example.json") or base.endswith(".schema.json")
    placeholder_check = is_placeholder_value if sample_doc else is_explicit_placeholder
    for line_no, rule in _find_secret_matches(text, placeholder_check):
        findings.append(_finding(
            "SECRET_PATTERN", "fail", rel_path, line_no,
            "命中 {} 形态的凭证特征（第 {} 行）；公开前请删除真实值或改为占位说明".format(rule, line_no)))
    for line_no, _address in find_personal_emails(text):
        findings.append(_finding(
            "PERSONAL_EMAIL", "fail", rel_path, line_no,
            "命中完整邮箱形态（第 {} 行）；请改用 example.com 占位或做脱敏".format(line_no)))
    for line_no, _path in find_home_paths(text):
        if task_doc:
            findings.append(_finding(
                "TASKS_PRIVATE_PATH", "fail", rel_path, line_no,
                "任务/决策记录中出现本机绝对路径（第 {} 行）；公开前请删除或改写为相对路径".format(line_no)))
        else:
            findings.append(_finding(
                "ABSOLUTE_HOME_PATH", "fail", rel_path, line_no,
                "命中本机绝对路径形态（第 {} 行）；请改为相对路径或占位变量".format(line_no)))
    return findings


def check_markdown_links(rel_path, text, root):
    findings = []
    base = rel_path.rsplit("/", 1)[-1]
    if not base.lower().endswith(".md"):
        return findings
    source_dir = (root / rel_path).parent
    for line_no, target in markdown_link_spans(text):
        if _is_external_link(target):
            continue
        path_part = target.split("#", 1)[0].strip()
        if not path_part:
            continue
        path_part = urllib.parse.unquote(path_part)
        if not path_part:
            continue
        if (source_dir / path_part).exists():
            continue
        findings.append(_finding(
            "MARKDOWN_LINKS", "fail", rel_path, line_no,
            "相对链接目标不存在（第 {} 行）；请修正路径或删除该链接".format(line_no)))
    return findings


def check_json_samples(rel_path, text):
    findings = []
    base = rel_path.rsplit("/", 1)[-1]
    if base.endswith(".example.json"):
        code = "EXAMPLE_JSON_VALID"
    elif base.endswith(".schema.json"):
        code = "SCHEMA_JSON_VALID"
    else:
        return findings
    try:
        json.loads(text)
    except json.JSONDecodeError as error:
        line = getattr(error, "lineno", 0) or 0
        findings.append(_finding(
            code, "fail", rel_path, line,
            "{} 无法解析为 JSON（JSONDecodeError，第 {} 行）；请修复 JSON 语法".format(
                "示例文件" if code == "EXAMPLE_JSON_VALID" else "schema 文件", line)))
    except ValueError:
        findings.append(_finding(
            code, "fail", rel_path, 0,
            "{} 无法解析为 JSON（ValueError）；请修复 JSON 语法".format(
                "示例文件" if code == "EXAMPLE_JSON_VALID" else "schema 文件")))
    return findings


def _worktree_root(root):
    result = _run_git(root, ["rev-parse", "--show-toplevel"])
    if result is None or result.returncode != 0:
        return None
    path = result.stdout.strip()
    if not path:
        return None
    return Path(path)


def _ignore_chain(rel_path, root):
    """Yield (ignore_dir, path_relative_to_that_dir) from deepest to shallowest."""
    parts = rel_path.split("/")[:-1]
    for depth in range(len(parts), 0, -1):
        directory = root.joinpath(*parts[:depth])
        relative = "/".join(parts[depth:]) + "/" + rel_path.rsplit("/", 1)[-1]
        yield directory, relative
    yield root, rel_path


def _local_ignore_decision(rel_path, root):
    """Decide one path against the .gitignore files of its own directories.

    The deepest .gitignore wins, exactly like Git: a rule in a nested
    directory overrides the rules of the parent directories.  Only an
    explicit rule produces a decision; a path without any matching rule
    stays "none".
    """
    top = _worktree_root(root)
    candidates = list(_ignore_chain(rel_path, root))
    if top is not None:
        try:
            base = Path(root).resolve().relative_to(top)
            relative = (base / rel_path).as_posix()
        except ValueError:
            relative = None
        if relative is not None:
            candidates.append((top, relative))
    for ignore_dir, relative in candidates:
        ignore_file = ignore_dir / ".gitignore"
        if not ignore_file.is_file():
            continue
        try:
            lines = read_text(ignore_file).splitlines()
        except OSError:
            continue
        decision = _ignore_decision(relative, lines)
        if decision in ("ignored", "not-ignored"):
            return decision == "ignored"
    return False


def is_ignored(rel_path, root):
    """Is the file covered by an ignore rule?

    The real Git decision is preferred; when the tree is not a Git work
    tree the local .gitignore files of the path's own directories are used
    with the same, well defined ordering.  Nothing is written either way.
    """
    decision = _git_check_ignore(root, rel_path)
    if decision is not None:
        return decision
    return _local_ignore_decision(rel_path, root)


def _skill_scope(root, all_paths):
    """Return (prefix, paths) limited to the Skill directory that is published.

    The private-layer rules describe the Skill's own `config/` and `state/`
    directories.  When the scanned root contains several directories the
    rules must not leak into unrelated trees, so only the paths below the
    resolved Skill directory are judged.
    """
    skill_dir = resolve_skill_dir(root, _skill_name())
    if skill_dir is None:
        return "", list(all_paths)
    prefix = skill_dir.relative_to(root).as_posix()
    if prefix == ".":
        prefix = ""
    scoped = []
    for rel in all_paths:
        if not prefix or rel == prefix or rel.startswith(prefix + "/"):
            scoped.append(rel)
    return prefix, scoped


def _is_single_skill_root(root):
    """Does the root hold exactly one Skill directory (or is itself one)?"""
    if (root / "SKILL.md").is_file():
        return True
    try:
        children = [child for child in sorted(root.iterdir())
                    if child.is_dir() and (child / "SKILL.md").is_file()]
    except OSError:
        return False
    return len(children) == 1


def check_local_config(all_paths, root):
    findings = []
    _prefix, scoped = _skill_scope(root, all_paths)
    for rel in scoped:
        parts = rel.split("/")
        if len(parts) < 2 or "config" not in parts[:-1]:
            continue
        name = parts[-1]
        if not re.search(r"\.local\.", name):
            continue
        findings.append(_finding(
            "LOCAL_CONFIG_PUBLISHED", "fail", rel, 0,
            "config 目录下的本机私有文件（*.local.*）进入了待发布清单；"
            "请保留本机原件，并把它从待发布清单中排除"))
    return findings


def _is_private_state_path(rel_path, prefix=""):
    """Is the path private runtime evidence below `state/`?

    Only the exact rule file `state/.gitignore` is allowed to live in the
    private state directory.  A nested rule file such as
    `state/nested/.gitignore` is evidence of its own and must not pass.
    """
    parts = rel_path.split("/")
    if len(parts) > 1 and parts[-2:] == ["state", ".gitignore"]:
        # The allowlist is position-relative: a repo-root path such as
        # skills/<skill>/state/.gitignore still resolves to the same rule.
        parts = parts[-2:]
    if prefix:
        scope = prefix.split("/")
        if parts[:len(scope)] == scope:
            parts = parts[len(scope):]
        elif len(parts) > 1 and parts[-2:] == ["state", ".gitignore"]:
            # Repo-root mode sees a Skill-prefixed state rule; treat the
            # last two components as its private-state scope.
            parts = parts[-2:]
    if "state" not in parts[:-1]:
        return False
    if parts[-1] != ".gitignore":
        return True
    # The rule file is only allowed directly inside the state directory,
    # so "state/.gitignore" passes and "state/nested/.gitignore" does not.
    return len(parts) != 2


def check_private_state(all_paths, root):
    """Private runtime evidence must never be part of the published tree.

    Only the `state/.gitignore` rule file may live inside the private state
    directory; every other file below `state/` is local evidence and must
    fail the gate, whether it is tracked, ignored or simply present on
    disk.
    """
    findings = []
    prefix, scoped = _skill_scope(root, all_paths)
    for rel in scoped:
        if not _is_private_state_path(rel, prefix):
            continue
        findings.append(_finding(
            "PRIVATE_STATE_PUBLISHED", "fail", rel, 0,
            "state/ 下的本机运行证据进入了待发布清单；"
            "请保留本机原件，并把它从待发布清单中排除"))
    return findings


def check_private_maintenance(all_paths, root):
    """Original task and decision records must remain untracked and local."""
    findings = []
    prefix, scoped = _skill_scope(root, all_paths)
    skill_base = prefix + "/" if prefix else ""
    for name in ("TASKS.md", "DECISIONS.md"):
        rel = skill_base + name
        if rel not in scoped:
            continue
        findings.append(_finding(
            "PRIVATE_MAINTENANCE_PUBLISHED", "fail", rel, 0,
            "原始维护记录进入了待发布清单；请保留本机原件并退出 Git 跟踪，"
            "不要用脱敏摘要替代原件"))
    return findings


def resolve_skill_dir(root, preferred_name):
    """Find the Skill directory that owns SKILL.md / CHANGELOG.md."""
    if (root / "SKILL.md").is_file():
        return root
    candidates = []
    try:
        for child in sorted(root.iterdir()):
            if child.is_dir() and (child / "SKILL.md").is_file():
                candidates.append(child)
    except OSError:
        return None
    if preferred_name:
        for child in candidates:
            if child.name == preferred_name:
                return child
    if len(candidates) == 1:
        return candidates[0]
    return None


def check_version_consistency(root, preferred_name):
    findings = []
    skill_dir = resolve_skill_dir(root, preferred_name)
    if skill_dir is None:
        findings.append(_finding(
            "VERSION_CONSISTENT", "fail", "SKILL.md", 0,
            "未找到 SKILL.md，无法确认版本一致"))
        return findings
    skill_rel = skill_dir.relative_to(root).as_posix() + "/SKILL.md"
    changelog_path = skill_dir / "CHANGELOG.md"
    changelog_rel = skill_dir.relative_to(root).as_posix() + "/CHANGELOG.md"
    if not changelog_path.is_file():
        findings.append(_finding(
            "VERSION_CONSISTENT", "fail", changelog_rel, 0,
            "缺少 CHANGELOG.md，无法确认版本一致"))
        return findings
    try:
        skill_version = skill_frontmatter_version(read_text(skill_dir / "SKILL.md"))
        changelog_version = latest_changelog_version(read_text(changelog_path))
    except OSError:
        findings.append(_finding(
            "VERSION_CONSISTENT", "fail", changelog_rel, 0,
            "读取版本文件失败，无法确认版本一致"))
        return findings
    if skill_version is None and changelog_version is None:
        findings.append(_finding(
            "VERSION_CONSISTENT", "fail", skill_rel, 0,
            "SKILL.md frontmatter 与 CHANGELOG.md 都没有可解析的版本号"))
    elif skill_version is None:
        findings.append(_finding(
            "VERSION_CONSISTENT", "fail", skill_rel, 0,
            "SKILL.md frontmatter 缺少 metadata.version，无法确认版本一致"))
    elif changelog_version is None:
        findings.append(_finding(
            "VERSION_CONSISTENT", "fail", changelog_rel, 0,
            "CHANGELOG.md 没有 '## [x.y.z]' 版本标题，无法确认版本一致"))
    elif skill_version != changelog_version:
        findings.append(_finding(
            "VERSION_CONSISTENT", "fail", skill_rel, 0,
            "版本不一致：SKILL.md metadata.version={}，CHANGELOG.md 最新版本={}".format(
                skill_version, changelog_version)))
    return findings


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

def build_report(root, manifest, all_paths, missing, unreadable, mode):
    findings = []
    for rel in manifest:
        full = root / rel
        text, problem = _decode_text(full)
        if problem is not None:
            findings.append(_finding(
                "FILE_UNREADABLE", "fail", rel, 0,
                "{}，未做内容检查；公开前请人工复核".format(problem)))
            continue
        findings.extend(check_text_content(rel, text))
        findings.extend(check_markdown_links(rel, text, root))
        findings.extend(check_json_samples(rel, text))
    findings.extend(check_local_config(all_paths, root))
    findings.extend(check_private_state(all_paths, root))
    findings.extend(check_private_maintenance(all_paths, root))
    findings.extend(check_version_consistency(root, _skill_name()))
    if missing and mode == "git":
        if _is_single_skill_root(root):
            # In a single-Skill tree a tracked file that is absent is a
            # hole in the tree that is about to be published, not a sparse
            # checkout of a bigger repository.
            for rel in missing:
                findings.append(_finding(
                    "FILE_MISSING", "fail", rel, 0,
                    "受 Git 跟踪的路径在工作树中不存在，未做内容检查；"
                    "公开前请恢复该文件或从版本库移除"))
        else:
            findings.append(_finding(
                "FILE_MISSING", "info", "", 0,
                "{} 个受 Git 跟踪的路径在工作树中不存在（稀疏检出或已删除），未做内容检查".format(len(missing))))
    for rel, reason in unreadable:
        findings.append(_finding(
            "FILE_UNREADABLE", "fail", rel, 0,
            "{}，未做内容检查；公开前请人工复核".format(reason)))
    findings.sort(key=lambda item: (item["code"], item["file"], item["line"]))
    summary = {"fail": 0, "warn": 0, "info": 0}
    for item in findings:
        summary[item["severity"]] = summary.get(item["severity"], 0) + 1
    return {
        "schema": SCHEMA,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "root": str(root),
        "files": len(manifest),
        "findings": findings,
        "summary": summary,
    }


def _skill_name():
    try:
        return Path(__file__).resolve().parents[1].name
    except (IndexError, OSError):
        return None


def save_report(path, report):
    """Write the report with owner-only permissions (0600)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    try:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        fd = os.open(target, os.O_WRONLY | os.O_TRUNC, 0o600)
        os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(payload)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        raise Refused("usage_error")


def _add_common(parser, suppress):
    default = argparse.SUPPRESS if suppress else None
    flag_default = argparse.SUPPRESS if suppress else False
    parser.add_argument("--root", default=default,
                        help="要检查的目录树；默认是本脚本所在 Skill 目录的父目录")
    parser.add_argument("--strict", action="store_true", default=flag_default,
                        help="任一 fail 或 warn 都以退出码 1 结束")
    parser.add_argument("--list-only", dest="list_only", action="store_true",
                        default=flag_default,
                        help="只打印待检查的文件清单（每行一个相对路径），不做内容检查")
    parser.add_argument("--output", default=default,
                        help="可选：把 JSON 报告写入该文件（权限 0600）")


EPILOG = """\
示例:
  python3 scripts/public_release_check.py --list-only
  python3 scripts/public_release_check.py --root magpie-optimizer
  python3 scripts/public_release_check.py --strict --output report.json

只读边界: 只读取目标目录树内的文件，并调用只读 git 命令（rev-parse /
ls-files）。不调用 Magpie CLI，不读取 ~/.config/magpie，不改网关，
不发起任何模型请求，也不消耗额度。唯一写入是可选的 --output 报告文件（0600）。
"""


def build_parser():
    parser = _Parser(description=__doc__,
                     formatter_class=argparse.RawDescriptionHelpFormatter,
                     epilog=EPILOG)
    _add_common(parser, suppress=False)
    sub = parser.add_subparsers(dest="command")
    check = sub.add_parser("check", help="执行发布前检查（默认子命令）",
                            formatter_class=argparse.RawDescriptionHelpFormatter,
                            epilog=EPILOG)
    _add_common(check, suppress=True)
    return parser


def resolve_root(value):
    if value is None:
        root = Path(__file__).resolve().parents[2]
    else:
        root = Path(value).expanduser()
    try:
        root = root.resolve()
    except OSError:
        raise Refused("root_not_resolvable")
    require(root.is_dir(), "root_not_found")
    return root


def main():
    parser = build_parser()
    args = parser.parse_args()
    command = getattr(args, "command", None) or "check"
    require(command == "check", "usage_error")
    root = resolve_root(getattr(args, "root", None))
    manifest, all_paths, missing, unreadable, _mode = collect_manifest(root)
    if getattr(args, "list_only", False):
        for rel in manifest:
            print(rel)
        return 0
    report = build_report(root, manifest, all_paths, missing, unreadable, _mode)
    output = getattr(args, "output", None)
    if output:
        save_report(output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    summary = report["summary"]
    if summary.get("fail", 0) > 0:
        return 1
    if getattr(args, "strict", False) and summary.get("warn", 0) > 0:
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (Refused, OSError, ValueError, KeyError, TypeError,
            subprocess.SubprocessError) as error:
        # Never echo upstream stdout/stderr, raw JSON or file contents: those
        # can carry accounts, credentials or private paths.
        reason = str(error) if isinstance(error, Refused) else type(error).__name__
        print(json.dumps({"status": "REFUSED", "reason": reason}), file=sys.stderr)
        sys.exit(2)
