#!/usr/bin/env python3
"""Focused repository profiles and explicit source-package state."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from auto_discover import REPO_PATTERN, atomic_json, github_get, read_json  # noqa: E402
from lockutil import write_lock  # noqa: E402
from project_context import CONCEPTS, discover, frontmatter, match_terms, terms_for  # noqa: E402
from star_query import emit, envelope  # noqa: E402


TEXT_BUDGET = 48_000
SKILL_LIMIT = 4
MANIFEST_LIMIT = 5
MEDIA_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".mp4", ".mov", ".webm",
    ".mp3", ".wav", ".flac", ".ogg", ".aac", ".m4a", ".ttf", ".otf", ".woff",
    ".woff2", ".glb", ".gltf", ".fbx", ".obj", ".stl", ".blend", ".usdz",
}
DEPENDENCY_NAMES = {
    "package.json", "requirements.txt", "pyproject.toml", "setup.py",
    "environment.yml", "Pipfile", "poetry.lock", "package-lock.json",
    "pnpm-lock.yaml", "yarn.lock", "uv.lock",
}
RUNTIME_TERMS = {
    "timeline": "timeline",
    "render": "rendering",
    "renderer": "rendering",
    "canvas": "canvas-rendering",
    "three.js": "three-js",
    "ffmpeg": "ffmpeg-composition",
    "subtitle": "subtitles",
    "captions": "subtitles",
    "tts": "text-to-speech",
    "voice": "voice-generation",
    "asr": "transcription",
    "whisper": "transcription",
    "music": "music-generation",
    "audio": "audio-processing",
    "mixing": "audio-mixing",
    "style": "style-system",
    "styleboard": "style-system",
    "avatar": "avatar",
    "lipsync": "lip-sync",
    "plugin interface": "plugin-system",
    "skill interface": "skill-interface",
    "command line": "cli",
    "http server": "server",
    "websocket server": "server",
}


def now_utc():
    return datetime.now(timezone.utc)


def digest(value):
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def valid_repo(name):
    if not REPO_PATTERN.fullmatch(name or ""):
        return False
    owner, repository = name.split("/")
    return all(part not in {"", ".", ".."} and not part.startswith(".") for part in (owner, repository))


def profile_paths(data_dir):
    directory = data_dir / "repository-profiles"
    return directory, directory / "focus.json"


def cache_path(data_dir, repo):
    directory, _ = profile_paths(data_dir)
    return directory / (repo.replace("/", "__") + ".json")


def decode_content(row):
    encoding = row.get("encoding")
    content = row.get("content") or ""
    if encoding == "base64":
        content = base64.b64decode(content, validate=False).decode("utf-8", "replace")
    elif encoding not in (None, "none", "utf-8"):
        raise ValueError("unsupported content encoding")
    return content


def bounded_text(value):
    return value[:TEXT_BUDGET], len(value) > TEXT_BUDGET


def fetch_optional(endpoint, errors, label, accept="application/vnd.github+json"):
    try:
        return github_get(endpoint, accept=accept)
    except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
        errors.append(f"{label}: {type(exc).__name__}")
        return None


def classify_tree(tree):
    rows = tree.get("tree") if isinstance(tree, dict) else None
    if not isinstance(rows, list):
        raise ValueError("malformed tree response")
    skills, dependencies, scripts, media, code, licenses = [], [], [], [], [], []
    extension_counts, directory_counts = Counter(), Counter()
    for row in rows:
        path = row.get("path") or ""
        if not isinstance(path, str) or path.startswith("."):
            continue
        kind = row.get("type")
        name = Path(path).name.lower()
        suffix = Path(path).suffix.lower()
        top = path.split("/", 1)[0]
        if kind == "tree":
            directory_counts[top] += 1
            continue
        if kind != "blob":
            continue
        if name == "skill.md":
            skills.append(path)
        if name in {"license", "licence", "copying", "credits", "credits.md", "notice"}:
            licenses.append(path)
        if name in DEPENDENCY_NAMES:
            dependencies.append(path)
        if suffix in {".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd"} or name in {"setup", "setup.py"}:
            scripts.append(path)
        if suffix in MEDIA_SUFFIXES:
            media.append(path)
        if suffix in {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".html",
                      ".css", ".sh", ".rs", ".go", ".java"}:
            code.append(path)
        if suffix:
            extension_counts[suffix] += 1
    return {
        "truncated": bool(tree.get("truncated")),
        "entries": len(rows),
        "skills": sorted(skills),
        "dependencies": sorted(dependencies),
        "scripts": sorted(scripts),
        "media": sorted(media),
        "code": sorted(code),
        "licenses": sorted(licenses),
        "top_directories": sorted(directory_counts, key=lambda k: (-directory_counts[k], k))[:20],
        "extension_counts": dict(extension_counts.most_common(20)),
    }


def fetch_limited(paths, commit, repo, kind, limit, errors):
    result = []
    for path in paths[:limit]:
        row = fetch_optional(
            f"repos/{repo}/contents/{path}?ref={commit}", errors, f"{kind}:{path}")
        if not isinstance(row, dict):
            continue
        try:
            text, truncated = bounded_text(decode_content(row))
            result.append({"path": path, "sha": row.get("sha"), "url": row.get("html_url"),
                           "text": text, "truncated": truncated})
        except (ValueError, TypeError) as exc:
            errors.append(f"{kind}:{path}: {type(exc).__name__}")
    return result


def parse_skill(text, path):
    try:
        metadata = frontmatter(text)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        return {"path": path, "valid": False, "error": type(exc).__name__}
    return {"path": path, "valid": True, "name": metadata.get("name"),
            "description": metadata.get("description")}


def infer_capabilities(paths_text, dependency_texts):
    # Prefer prose and dependency text. Tree paths are architecture hints, not prose:
    # a directory named "scripts" must not turn every repository into a CLI.
    prose = paths_text[:5] + [row.get("text", "") for row in dependency_texts]
    text = " ".join(prose).lower()
    capabilities = []
    for needle, label in RUNTIME_TERMS.items():
        if re.search(r"(?<![a-z0-9])" + re.escape(needle) + r"s?(?![a-z0-9])", text,
                     flags=re.IGNORECASE):
            capabilities.append(label)
    return sorted(capabilities)


def infer_kind(repo, facts, skills, capabilities):
    has_skill = bool(skills)
    media = len(facts["media"])
    code = len(facts["code"])
    dependencies = len(facts["dependencies"])
    if has_skill and (code > 8 or dependencies >= 1 or media > 8):
        kind = "skill-backed runtime/repository"
    elif has_skill and facts["entries"] <= 120 and code <= 40 and media <= 40:
        kind = "skill repository"
    elif media > max(code * 2, 40):
        kind = "asset/style-heavy repository"
    elif code > 40 or dependencies >= 2:
        kind = "application/runtime repository"
    else:
        kind = "unknown repository shape"
    return kind


def suggested_sparse_paths(facts):
    """Prefer implementation and Skill launchers; leave bulky demo/media assets upstream."""
    roots = {path for path in facts["dependencies"] if "/" not in path}
    roots.update(path for path in facts["licenses"] if "/" not in path)
    for path in facts["skills"]:
        parts = path.split("/")
        roots.add("/".join(parts[:-1]) if len(parts) > 1 else parts[0])
    skill_directories = {str(Path(path).parent) for path in facts["skills"]}
    implementation_roots = {"core", "src", "app", "lib"}
    for path in facts["code"]:
        top = path.split("/", 1)[0]
        if top in implementation_roots:
            roots.add(top)
        elif top == "styleboard":
            roots.update(path for path in facts["code"] + facts["dependencies"]
                         if path.startswith(top + "/") and Path(path).suffix in
                         {".py", ".json", ".sh", ".js", ".mjs"})
    roots.update(skill_directories)
    roots.update(path for path in facts["dependencies"] if "/" in path)
    # Dependency manifests under demo/style folders are not runtime entrypoints;
    # avoid recommending dozens of style demo lockfiles by default.
    roots.difference_update(path for path in list(roots)
                            if path.startswith("styles/") and path.endswith(
                                ("package.json", "package-lock.json")))
    return sorted(roots)


def local_reference_snapshots(repo, roots):
    """Find immutable snapshots already curated by an installed Skill."""
    slug = repo.replace("/", "--")
    result = []
    for root in roots:
        root_path = Path(root)
        libraries = []
        if root_path.is_dir():
            libraries.append(root_path / "reference-library")
            libraries.extend(path / "reference-library" for path in root_path.glob("*") if path.is_dir())
        for library in libraries:
            source = library / "sources" / slug
            if not source.is_dir():
                continue
            commit = None
            if (source / ".git").exists():
                try:
                    commit = run_git(["git", "-C", str(source), "rev-parse", "HEAD"])
                except (OSError, RuntimeError, subprocess.TimeoutExpired):
                    pass
            catalog_entry = None
            readme = library / "README.md"
            if readme.is_file():
                try:
                    text = readme.read_text(encoding="utf-8", errors="replace")
                    marker = "sources/" + slug + "/"
                    position = text.find(marker)
                    if position >= 0:
                        tail = text[position + len(marker): position + len(marker) + 400]
                        match = re.search(r"`([0-9a-f]{7,40})`", tail)
                        if match:
                            catalog_entry = match.group(1)
                except OSError:
                    pass
            pinned = commit or catalog_entry
            result.append({
                "path": str(source), "commit": pinned,
                "git_commit": commit, "catalog_commit": catalog_entry,
                "status": "existing-local-snapshot",
                "upstream_commit_comparison": "local pinned commit compared with profile head by the Agent",
            })
    return result

def local_matches(repo, text, skills, roots, project=None):
    profiles, warnings = discover(roots, project)
    source = " ".join([repo, text, " ".join(s.get("description") or "" for s in skills if s.get("valid"))])
    upstream = terms_for(source)
    rows = []
    concept_terms = {alias for aliases in CONCEPTS for alias in aliases}
    priority_concepts = {"video", "视频", "成片", "animation", "动画", "动效",
                         "render", "rendering", "渲染", "voice", "tts", "配音", "语音合成"}
    for profile in profiles:
        hits = match_terms(profile, {"_search_terms": upstream})
        primary = match_terms({"search_terms": profile.get("primary_terms", profile["search_terms"]),
                               "_search_terms": upstream}, {"_search_terms": upstream})
        concepts = sorted(set(primary) & concept_terms)
        if not concepts:
            continue
        rows.append({
            "project_id": profile["project_id"], "skill_path": profile["skill_path"],
            "matched_terms": hits, "primary_matches": primary,
            "domain_concepts": concepts,
            "target_activity": profile["activity"], "target_revision": profile["target_revision"],
        })
    rows.sort(key=lambda row: (-len(set(row["domain_concepts"]) & priority_concepts),
                               -len(row["domain_concepts"]), -len(row["primary_matches"]),
                               -len(row["matched_terms"]), row["project_id"]))
    return rows[:20], warnings


def build_profile(repo, data_dir, roots, project=None):
    if not valid_repo(repo):
        raise ValueError("Invalid owner/repo")
    meta = github_get(f"repos/{repo}")
    branch = meta.get("default_branch")
    if not isinstance(branch, str) or not branch:
        raise ValueError("Missing default branch")
    errors = []
    branch_meta = fetch_optional(f"repos/{repo}/branches/{branch}", errors, "default branch head")
    commit = branch_meta.get("commit", {}).get("sha") if isinstance(branch_meta, dict) else None
    if not isinstance(commit, str) or not commit:
        raise ValueError("Default branch head unavailable")
    tree = fetch_optional(f"repos/{repo}/git/trees/{commit}?recursive=1", errors, "tree")
    if not isinstance(tree, dict):
        raise ValueError("Repository tree unavailable")
    facts = classify_tree(tree)
    errors.extend(f"tree truncated ({facts['entries']} entries)" for _ in [0] if facts["truncated"])
    readme_row = fetch_optional(f"repos/{repo}/readme", errors, "readme")
    readme = None
    if isinstance(readme_row, dict):
        try:
            text, truncated = bounded_text(decode_content(readme_row))
            readme = {"path": readme_row.get("path"), "blob_sha": readme_row.get("sha"),
                      "url": readme_row.get("html_url"), "text": text, "truncated": truncated}
        except (ValueError, TypeError):
            errors.append("readme: decode failed")
    skill_docs = fetch_limited(facts["skills"], commit, repo, "skill", SKILL_LIMIT, errors)
    skills = [parse_skill(row["text"], row["path"]) for row in skill_docs]
    dependency_docs = fetch_limited(facts["dependencies"], commit, repo, "dependency", MANIFEST_LIMIT, errors)
    combined_text = [repo, meta.get("description") or "", " ".join(meta.get("topics") or []),
                     (readme or {}).get("text", "")]
    capabilities = infer_capabilities(combined_text, dependency_docs)
    kind = infer_kind(meta, facts, skills, capabilities)
    matches, match_warnings = local_matches(repo, " ".join(combined_text), skills, roots, project)
    snapshots = local_reference_snapshots(repo, roots)
    profile = {
        "schema_version": "repository-profile/1.0", "repo": repo,
        "repo_id": meta.get("id"), "default_branch": branch, "head_commit": commit,
        "fetched_at": now_utc().isoformat(), "status": "complete" if not errors else "partial",
        "errors": errors,
        "identity": {key: meta.get(key) for key in (
            "description", "topics", "license", "stargazers_count", "language",
            "pushed_at", "archived", "html_url")},
        "tree": facts,
        "readme": readme,
        "skill_units": skills,
        "dependency_documents": dependency_docs,
        "capabilities_inferred": capabilities,
        "repository_kind_inferred": kind,
        "local_matches": matches,
        "license_assessment": {
            "declared_license": meta.get("license"),
            "license_paths": facts["licenses"][:20],
            "license_paths_truncated": len(facts["licenses"]) > 20,
            "license_path_count": len(facts["licenses"]),
            "media_entries": len(facts["media"]),
            "warning": "Repository license does not automatically cover bundled media, fonts, models, music, or style assets; inspect credits and asset-specific licenses before reuse." if facts["media"] else None,
        },
        "reuse_assessment": {
            "status": "needs_review",
            "allowed_conclusions": ["upstream capability package", "production backend/style library",
                                    "selected methods only", "not applicable or unsafe"],
            "must_verify": [
                "Run one bounded sample through the upstream interface before claiming direct production use.",
                "Compare its output contract with each matched local Skill; do not expand a local Skill's stated exclusions.",
                "Check asset, font, model, and music licenses separately from the repository license.",
                "Inspect dependency size and setup scripts before installation; profile evidence is not execution evidence.",
            ],
        },
        "local_snapshots": snapshots,
        "source_package": {
            "default_strategy": "none; API profile is sufficient for initial review",
            "recommended_strategy": ("existing-local-snapshot; compare its pinned commit with upstream before materializing another package" if snapshots else
                                     "bounded source package pinned to commit"
                                     if kind == "skill-backed runtime/repository"
                                     or any(len(row["domain_concepts"]) >= 2 for row in matches) else "none"),
            "recommended_paths": [],
            "materialize_requires": "source-package create with explicit paths, target directory, and a byte budget",
            "update_policy": "read remote status first; update only a clean pinned checkout and retain the previous commit in the manifest",
        },
        "profile_revision": None,
    }
    if profile["source_package"]["recommended_strategy"].startswith("bounded source package"):
        profile["source_package"]["recommended_paths"] = suggested_sparse_paths(facts)
    for snapshot in snapshots:
        if snapshot.get("commit") and snapshot["commit"] != commit:
            if len(snapshot["commit"]) < 40:
                prefix = snapshot["commit"]
                snapshot["upstream_commit_comparison"] = "different-prefix" if not commit.startswith(prefix) else "same-prefix"
            else:
                snapshot["upstream_commit_comparison"] = "different" if snapshot["commit"] != commit else "same"
        else:
            snapshot["upstream_commit_comparison"] = "unknown"
    profile["profile_revision"] = digest({
        "repo_id": profile["repo_id"], "pushed_at": profile["identity"]["pushed_at"],
        "readme": profile["readme"] and profile["readme"]["blob_sha"],
        "skills": [(s["path"], s.get("name"), s.get("description")) for s in skills],
        "tree": {key: facts[key] for key in ("entries", "truncated", "skills", "dependencies", "media", "code")},
    })
    path = cache_path(data_dir, repo)
    if profile["status"] == "complete":
        atomic_json(path, profile)
    elif not path.exists():
        atomic_json(path, profile)
    warnings = match_warnings.copy()
    if facts["truncated"]:
        warnings.append("Repository tree was truncated; source package may be needed for complete inventory")
    if len(facts["skills"]) > SKILL_LIMIT:
        warnings.append(f"Only first {SKILL_LIMIT} of {len(facts['skills'])} Skill documents fetched")
    if profile["status"] == "partial":
        warnings.append("Partial profile retained alongside the last complete cache when applicable")
    return profile, warnings


def load_focus(data_dir):
    _, path = profile_paths(data_dir)
    value = read_json(path, {"schema_version": "focus/1.0", "repositories": {}})
    if not isinstance(value, dict) or not isinstance(value.get("repositories"), dict):
        raise ValueError("Invalid focus state")
    return value


def save_focus(data_dir, value):
    directory, _ = profile_paths(data_dir)
    with atomic_context(directory):
        current = load_focus(data_dir)
        current["repositories"].update(value.get("repositories", {}))
        for name in value.get("_removed", []):
            current["repositories"].pop(name, None)
        current["updated_at"] = now_utc().isoformat()
        atomic_json(profile_paths(data_dir)[1], current)
    return current


class atomic_context:
    def __init__(self, directory):
        self.directory = directory
    def __enter__(self):
        self.lock = write_lock(self.directory)
        self.lock.__enter__()
        return self
    def __exit__(self, *args):
        return self.lock.__exit__(*args)


def cmd_profile(args):
    data_dir = args.data_dir.expanduser().resolve()
    try:
        profile, warnings = build_profile(args.repo, data_dir, args.skills_root, args.project)
    except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
        cached = read_json(cache_path(data_dir, args.repo))
        if cached and cached.get("status") == "complete" and cached.get("repo") == args.repo:
            result = envelope([cached], coverage={"repositories": 1},
                              warnings=[f"Profile refresh failed; serving last complete cache: {type(exc).__name__}"],
                              errors=[str(exc)], extra={"cached_at": str(cache_path(data_dir, args.repo))})
            result["snapshot_completeness"] = "not_applicable"
            result["status"] = "partial"
            return emit(result, 2)
        raise
    result = envelope([profile], coverage={"repositories": 1}, warnings=warnings,
                      extra={"cached_at": str(cache_path(data_dir, args.repo))})
    result["snapshot_completeness"] = "not_applicable"
    result["status"] = "partial" if warnings or profile["status"] != "complete" else "ok"
    return emit(result)


def cmd_focus(args):
    data_dir = args.data_dir.expanduser().resolve()
    if args.action == "list":
        value = load_focus(data_dir)
        result = envelope(list(value.get("repositories", {}).values()),
                          coverage={"repositories": len(value.get("repositories", {}))},
                          extra={"focus_path": str(profile_paths(data_dir)[1])})
        result["snapshot_completeness"] = "not_applicable"
        result["status"] = "ok"
        return emit(result)
    if not valid_repo(args.repo):
        return emit(envelope([], errors=["Invalid owner/repo"]), 1)
    if args.action == "add":
        row = {"repo": args.repo, "reason": args.reason or "", "added_at": now_utc().isoformat()}
        state = save_focus(data_dir, {"repositories": {args.repo: row}})
    elif args.action == "remove":
        state = save_focus(data_dir, {"repositories": {}, "_removed": [args.repo]})
    else:
        raise ValueError("Unknown focus action")
    result = envelope([state.get("repositories", {}).get(args.repo)],
                      coverage={"repositories": len(state.get("repositories", {}))},
                      extra={"focus_path": str(profile_paths(data_dir)[1])})
    result["snapshot_completeness"] = "not_applicable"
    result["status"] = "ok"
    return emit(result)


def manifest_path(data_dir, name):
    return data_dir / "repository-profiles" / "source-packages" / (name.replace("/", "__") + ".json")


def run_git(command, cwd=None, timeout=120):
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True,
                            timeout=timeout, check=False,
                            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    if result.returncode:
        raise RuntimeError(f"git failed ({result.returncode}): {command[1] if len(command) > 1 else command}")
    return result.stdout.strip()


def estimate_package_bytes(repo, commit, requested_paths):
    tree = github_get(f"repos/{repo}/git/trees/{commit}?recursive=1")
    rows = tree.get("tree") if isinstance(tree, dict) else None
    if not isinstance(rows, list):
        raise ValueError("Package size tree unavailable")
    if tree.get("truncated"):
        raise ValueError("Repository tree truncated; cannot bound package size")
    valid_rows = [row for row in rows if row.get("type") == "blob"]
    selected = effective_sparse_rows(valid_rows, requested_paths)
    return sum(int(row.get("size") or 0) for row in selected), len(selected)


def sparse_selection(row, requested_paths):
    path = row.get("path") or ""
    if row.get("type") != "blob" or not requested_paths:
        return False
    normalized = set(requested_paths)
    if path in normalized:
        return True
    return any(path.startswith(prefix.rstrip("/") + "/") for prefix in normalized
               if prefix.rstrip("/") != ".")


def effective_sparse_rows(rows, requested_paths):
    if not requested_paths:
        return list(rows)
    requested_roots = {path.rstrip("/") for path in requested_paths}
    return [row for row in rows if sparse_selection(row, requested_paths)
            or "/" not in (row.get("path") or "")]


def source_manifest(data_dir, repo):
    path = manifest_path(data_dir, repo)
    value = read_json(path)
    if not value or value.get("repo") != repo:
        raise ValueError("Source package manifest missing or mismatched")
    return value, path


def cmd_package_create(args):
    try:
        return _cmd_package_create(args)
    except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
        return emit(envelope([], errors=[str(exc)]), 1)


def _cmd_package_create(args):
    if not valid_repo(args.repo):
        return emit(envelope([], errors=["Invalid owner/repo"]), 1)
    if args.target is None:
        return emit(envelope([], errors=["--target is required for source-package create"]), 1)
    data_dir = args.data_dir.expanduser().resolve()
    target = args.target.expanduser().resolve()
    if target.exists() and any(target.iterdir()):
        return emit(envelope([], errors=["Target directory is not empty"]), 1)
    remote = f"https://github.com/{args.repo}.git"
    head = run_git(["git", "ls-remote", remote, "HEAD"]).split()[0]
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        raise ValueError("Invalid remote HEAD")
    tree = github_get(f"repos/{args.repo}/git/trees/{head}?recursive=1")
    rows = tree.get("tree") if isinstance(tree, dict) else None
    if not isinstance(rows, list):
        raise ValueError("Package size tree unavailable")
    if tree.get("truncated"):
        raise ValueError("Repository tree truncated; cannot bound package size")
    valid_rows = [row for row in rows if row.get("type") == "blob"]
    effective_rows = effective_sparse_rows(valid_rows, args.path or [])
    estimated_bytes = sum(int(row.get("size") or 0) for row in effective_rows)
    selected_files = len(effective_rows)
    if estimated_bytes > args.max_bytes:
        return emit(envelope([], errors=[
            f"Requested source package is {estimated_bytes} bytes, exceeding the explicit {args.max_bytes}-byte budget"]), 1)
    target.parent.mkdir(parents=True, exist_ok=True)
    # A non-empty target is rejected above, so this directory is ours to manage
    # and must be removed if any later step fails.
    created_target = True
    try:
        run_git(["git", "clone", "--depth", "1", "--filter=blob:none", "--no-checkout", remote, str(target)], timeout=300)
        created_target = True
        if args.path:
            patterns = []
            for path in args.path:
                normalized = path.rstrip("/")
                if not normalized or normalized in {".", ".."} or normalized.startswith(("/", "..", "\\")):
                    raise ValueError(f"Invalid sparse path: {path}")
                if not any(row.get("path") == normalized or row.get("path").startswith(normalized + "/")
                           for row in rows if row.get("type") in {"blob", "tree"}):
                    if created_target:
                        shutil.rmtree(target)
                    return emit(envelope([], errors=[
                        f"Sparse path not found in repository tree: {path}"]), 1)
                patterns.append("/" + normalized)
            run_git(["git", "-C", str(target), "sparse-checkout", "set", "--no-cone", *patterns])
        run_git(["git", "-C", str(target), "checkout", "--detach", head], timeout=180)
    except BaseException:
        if created_target:
            shutil.rmtree(target)
        raise
    manifest = {"schema_version": "source-package/1.0", "repo": args.repo,
                "commit": head, "created_at": now_utc().isoformat(),
                "updated_at": now_utc().isoformat(), "target": str(target),
                "paths": args.path, "strategy": "depth-1 blob-filtered non-cone sparse clone",
                "previous_commit": None, "executed_upstream_code": False,
                "estimated_blob_bytes": estimated_bytes, "selected_files": selected_files}
    atomic_json(manifest_path(data_dir, args.repo), manifest)
    return emit(package_envelope([manifest]))


def git_state(target):
    current = run_git(["git", "-C", str(target), "rev-parse", "HEAD"])
    dirty = bool(run_git(["git", "-C", str(target), "status", "--porcelain"]))
    return current, dirty


def cmd_package_status(args):
    data_dir = args.data_dir.expanduser().resolve()
    manifest, path = source_manifest(data_dir, args.repo)
    target = Path(manifest["target"])
    current, dirty = git_state(target)
    remote = run_git(["git", "ls-remote", f"https://github.com/{args.repo}.git", "HEAD"]).split()[0]
    row = {**manifest, "current_commit": current, "matches_manifest": current == manifest["commit"],
           "dirty": dirty, "remote_head": remote, "update_available": remote != manifest["commit"],
           "status": "clean" if current == manifest["commit"] and not dirty else "drifted",
           "manifest_path": str(path)}
    return emit(package_envelope([row]))


def cmd_package_update(args):
    data_dir = args.data_dir.expanduser().resolve()
    manifest, path = source_manifest(data_dir, args.repo)
    target = Path(manifest["target"])
    current, dirty = git_state(target)
    if dirty or current != manifest["commit"]:
        return emit(envelope([], errors=["Source package drifted; preserve local changes before update"]), 1)
    remote = run_git(["git", "ls-remote", f"https://github.com/{args.repo}.git", "HEAD"]).split()[0]
    if remote == current:
        return emit(package_envelope([{**manifest, "update_available": False}]))
    run_git(["git", "-C", str(target), "fetch", "--depth", "1", "origin", "HEAD"], timeout=300)
    fetched = run_git(["git", "-C", str(target), "rev-parse", "FETCH_HEAD"])
    run_git(["git", "-C", str(target), "checkout", "--detach", fetched], timeout=180)
    updated = {**manifest, "previous_commit": current, "commit": remote,
                "updated_at": now_utc().isoformat(), "executed_upstream_code": False,
                "remote_head_at_update": remote}
    atomic_json(path, updated)
    return emit(package_envelope([updated]))


def positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def package_envelope(items, **extra):
    result = envelope(items, coverage={"packages": len(items)}, extra=extra or None)
    result["snapshot_completeness"] = "not_applicable"
    result["status"] = "ok"
    return result


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    profile = sub.add_parser("profile", help="Build a bounded API repository profile")
    profile.add_argument("repo")
    profile.add_argument("--data-dir", type=Path, required=True)
    profile.add_argument("--skills-root", action="append", type=Path)
    profile.add_argument("--project")
    profile.set_defaults(func=cmd_profile)
    focus = sub.add_parser("focus", help="Add/list/remove a focused repository")
    focus.add_argument("action", choices=["add", "list", "remove"])
    focus.add_argument("repo", nargs="?")
    focus.add_argument("--reason")
    focus.add_argument("--data-dir", type=Path, required=True)
    focus.set_defaults(func=cmd_focus)
    package = sub.add_parser("source-package", help="Create/status/update an explicit source package")
    package.add_argument("action", choices=["create", "status", "update"])
    package.add_argument("repo")
    package.add_argument("--data-dir", type=Path, required=True)
    package.add_argument("--target", type=Path)
    # Only create mutates a target; status/update read it from the manifest.
    package.add_argument("--path", action="append")
    package.add_argument("--max-bytes", type=positive, default=256_000_000,
                         help="Reject packages whose selected Git blobs exceed this size")
    package.set_defaults(func=lambda args: {
        "create": cmd_package_create, "status": cmd_package_status,
        "update": cmd_package_update}[args.action](args))
    return root


def main():
    args = parser().parse_args()
    try:
        return args.func(args)
    except BrokenPipeError:
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        return emit(envelope([], errors=[str(exc)]), 1)


if __name__ == "__main__":
    raise SystemExit(main())
