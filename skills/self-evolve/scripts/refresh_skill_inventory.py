#!/usr/bin/env python3
"""Refresh the deterministic Self Evolve skill inventory.

This command only writes the inventory index. LLM-derived portraits and the
skill-chain graph have independent files and are never touched here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

from self_evolve_paths import (
    RUNTIME_ROOT,
    SKILL_ROOT,
    assert_external_write_path,
    assert_runtime_ready,
)


INVENTORY_SCHEMA_VERSION = "0.2"
CORE_SKILLS_YAML = SKILL_ROOT / "config" / "core_skills.yaml"

# 默认 skill 来源:用户级常见 agent 的 skill 目录(~/.<agent>/skills 约定)。
# 只收录实际存在的目录——无论用户用哪个 agent,inventory 都能开箱覆盖,
# 不写死任何个人路径。同一 skill 在多个 agent 目录用 symlink 共享时,
# build_inventory 按 realpath 自动去重。存在性由 _default_sources() 的 is_dir 兜底,
# 所以即便某个 agent 未安装或不用 skills/ 约定,也会被安静跳过。
_DEFAULT_AGENT_SKILL_DIRS = [
    # 主流编程 agent
    ("claude", ".claude/skills"),
    ("codex", ".codex/skills"),
    ("opencode", ".opencode/skills"),
    ("openclaw", ".openclaw/skills"),
    ("hermes", ".hermes/skills"),
    ("agents", ".agents/skills"),
    ("cursor", ".cursor/skills"),
    ("windsurf", ".windsurf/skills"),
    ("gemini", ".gemini/skills"),
    ("copilot", ".copilot/skills"),
    ("trae", ".trae/skills"),
    ("trae-cn", ".trae-cn/skills"),
    # WorkBuddy / CodeBuddy
    ("workbuddy", ".workbuddy/skills"),
    ("codebuddy", ".codebuddy/skills"),
    # Qoder 系
    ("qoder", ".qoder/skills"),
    ("qoderwork", ".qoderwork/skills"),
    ("qoderworkcn", ".qoderworkcn/skills"),
    # Qwen 系
    ("qwen", ".qwen/skills"),
    ("qwenworkcn", ".qwenworkcn/skills"),
    # 其他常见模型厂商 agent
    ("kimi", ".kimi/skills"),
    ("kimi-code", ".kimi-code/skills"),
    ("deepseek", ".deepseek/skills"),
    ("grok", ".grok/skills"),
    ("minimax", ".minimax/skills"),
    ("minimax-agent-cn", ".minimax-agent-cn/skills"),
]


def _default_sources() -> dict[str, Path]:
    """收集本机实际存在的标准 agent skill 目录,作为 config 缺失时的默认来源。"""
    sources: dict[str, Path] = {}
    for alias, rel in _DEFAULT_AGENT_SKILL_DIRS:
        path = Path.home() / rel
        if path.is_dir():
            sources[alias] = path
    return sources


DEFAULT_SOURCES = _default_sources()


def load_sources_from_config(config_path: Path) -> dict[str, Path]:
    """Load optional source aliases; a present-but-uninterpretable config fails loudly.

    合同（UP-CFG/A-F2）：文件缺失 → {}（默认来源）；存在但无法解释
    （PyYAML 缺失、YAML 损坏、顶层非映射、skill_sources 非映射）→ ValueError，
    绝不静默丢个人来源。
    """
    if not config_path.exists():
        return {}
    try:
        import yaml
    except ImportError as exc:
        raise ValueError(
            f"存在 {config_path} 但无法解析: 缺少 PyYAML。请 pip install pyyaml,"
            "或删除该文件以仅用默认 agent 目录来源"
        ) from exc
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"无法读取 skill_sources 配置 {config_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(
            f"{config_path} 顶层必须是映射(skill_sources: ...),现在是 {type(data).__name__}"
        )
    raw_sources = data.get("skill_sources", {})
    if raw_sources in (None, {}):
        return {}
    if not isinstance(raw_sources, dict):
        raise ValueError(
            f"{config_path} 的 skill_sources 必须是 '别名: 路径' 映射,"
            f"现在是 {type(raw_sources).__name__}"
        )
    sources: dict[str, Path] = {}
    for alias, path in raw_sources.items():
        # 合同（A-F2-R1）：先验证类型再判空——布尔/数字/容器等假值不是"禁用"，
        # 是错误 schema，静默跳过会丢个人来源。
        if not isinstance(alias, str) or not alias.strip():
            raise ValueError(f"{config_path} 的 skill_sources 含空别名键")
        if not isinstance(path, str) or not path.strip():
            raise ValueError(
                f"{config_path} 的 skill_sources.{alias} 必须是非空字符串路径,"
                f"现在是 {type(path).__name__} 值 {path!r}"
            )
        sources[alias] = Path(path).expanduser()
    return sources


def parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        return {}

    data: dict[str, str] = {}
    current_key = ""
    current_lines: list[str] = []

    def flush_multiline() -> None:
        nonlocal current_key, current_lines
        if current_key:
            data[current_key] = "\n".join(current_lines).strip()
            current_key = ""
            current_lines = []

    for line in text[4:end].strip().splitlines():
        if current_key:
            if line.startswith("  ") or not re.match(r"^[A-Za-z0-9_-]+:", line):
                current_lines.append(line.strip())
                continue
            flush_multiline()
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key, value = key.strip(), value.strip()
        if value in {"|", ">"}:
            current_key = key
            current_lines = []
        else:
            data[key] = value.strip("'\"")
    flush_multiline()
    return data


def first_heading(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def _resolved(path: Path) -> Path:
    try:
        return path.expanduser().resolve(strict=False)
    except OSError:
        return path.expanduser().absolute()


def _skill_key(skill_id: str, resolved_dir: Path) -> str:
    """Keep duplicate names distinct while remaining stable for one real path."""
    path_digest = hashlib.sha256(str(resolved_dir).encode("utf-8")).hexdigest()[:16]
    # A colon is already accepted by scheduler_run.py's bounded CLI allowlist.
    return f"{skill_id}:{path_digest}"


def _skill_md_candidates(source_path: Path) -> list[Path]:
    candidates: list[Path] = []
    if (source_path / "SKILL.md").is_file():
        candidates.append(source_path / "SKILL.md")
    candidates.extend(source_path.glob("*/SKILL.md"))
    return sorted(candidates, key=lambda path: str(path))


def scan_source(source_key: str, source_path: Path) -> list[dict]:
    """Scan one alias. ``build_inventory`` performs cross-alias realpath merge."""
    source_path = source_path.expanduser()
    if not source_path.exists():
        return []

    skills: list[dict] = []
    for discovered_md in _skill_md_candidates(source_path):
        skill_dir = _resolved(discovered_md.parent)
        skill_md = skill_dir / "SKILL.md"
        try:
            raw = skill_md.read_bytes()
            text = raw.decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        frontmatter = parse_frontmatter(text)
        skill_id = skill_dir.name
        description = frontmatter.get("description", "").strip()
        if len(description) > 500:
            description = description[:500].rstrip() + "..."
        try:
            modified_at = int(skill_md.stat().st_mtime)
        except OSError:
            modified_at = 0

        skills.append(
            {
                "skill_key": _skill_key(skill_id, skill_dir),
                "id": skill_id,
                "name": frontmatter.get("name", skill_id),
                "title": first_heading(text),
                "description": description,
                "version": frontmatter.get("version", ""),
                "license": frontmatter.get("license", ""),
                "source": source_key,
                "source_aliases": [source_key],
                "path": str(skill_dir),
                "skill_md": str(skill_md),
                "modified_at": modified_at,
                "content_hash": hashlib.sha256(raw).hexdigest(),
                "_realpath": str(skill_dir),
            }
        )
    return skills


def build_inventory(sources: dict[str, Path]) -> dict:
    """Build a realpath-deduplicated inventory from named source aliases."""
    by_realpath: dict[str, dict] = {}
    for source_alias, source_path in sources.items():
        for skill in scan_source(source_alias, source_path):
            realpath = skill["_realpath"]
            existing = by_realpath.get(realpath)
            if existing is None:
                by_realpath[realpath] = skill
                continue
            aliases = set(existing.get("source_aliases", []))
            aliases.update(skill.get("source_aliases", []))
            existing["source_aliases"] = sorted(aliases)

    skills = list(by_realpath.values())
    for skill in skills:
        skill.pop("_realpath", None)
        skill["source_aliases"] = sorted(set(skill.get("source_aliases", [])))
        # Preserve the first configured alias as the compatibility-facing
        # primary source; expose every equivalent alias separately.
        skill["source"] = skill.get("source") or skill["source_aliases"][0]
    skills.sort(key=lambda item: (item["id"], item["skill_key"]))

    return {
        "schema_version": INVENTORY_SCHEMA_VERSION,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "generated_epoch": int(time.time()),
        "sources": {key: str(path.expanduser()) for key, path in sources.items()},
        "skills": skills,
    }


def render_markdown(inventory: dict) -> str:
    lines = [
        "# Self Evolve Inventory",
        "",
        f"生成时间：{inventory['generated_at']}",
        f"Skill 总数：{len(inventory['skills'])}",
        "",
        "## 来源",
        "",
    ]
    for alias, path in inventory["sources"].items():
        lines.append(f"- `{alias}`：`{path}`")
    lines.extend(
        [
            "",
            "## Skill 列表",
            "",
            "| Skill Key | Name | Sources | Version | Description |",
            "|-----------|------|---------|---------|-------------|",
        ]
    )
    for skill in inventory["skills"]:
        description = skill.get("description", "").replace("\n", " ")
        if len(description) > 120:
            description = description[:120].rstrip() + "..."
        aliases = ", ".join(skill.get("source_aliases", [])) or "-"
        lines.append(
            f"| `{skill['skill_key']}` | `{skill['id']}` | {aliases} | "
            f"{skill.get('version') or '-'} | {description or '-'} |"
        )
    return "\n".join(lines).rstrip() + "\n"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
        os.chmod(path, 0o600)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh Self Evolve skill inventory.")
    parser.add_argument("--output-json", type=Path, default=RUNTIME_ROOT / "skill-inventory.json")
    parser.add_argument("--output-md", type=Path, default=RUNTIME_ROOT / "skill-inventory.md")
    parser.add_argument("--config", type=Path, default=CORE_SKILLS_YAML)
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        metavar="KEY=PATH",
        help="Override/add source directory, e.g. private-skills=/path/to/skills",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    try:
        assert_runtime_ready()
        args.output_json = assert_external_write_path(args.output_json, label="output_json")
        args.output_md = assert_external_write_path(args.output_md, label="output_md")
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    # merge:常见 agent 目录(DEFAULT)打底,个人 config 补充并 override 同名。
    # 这样“没有个人配置 → 扫默认 agent 目录”;“有个人配置 → 不强行覆盖,只补充”。
    try:
        configured_sources = load_sources_from_config(args.config)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    sources = {**DEFAULT_SOURCES, **configured_sources}
    for item in args.source:
        if "=" not in item:
            raise SystemExit(f"source must be KEY=PATH: {item}")
        alias, value = item.split("=", 1)
        if not alias.strip() or not value.strip():
            raise SystemExit(f"source must be KEY=PATH: {item}")
        sources[alias.strip()] = Path(value.strip()).expanduser()

    inventory = build_inventory(sources)
    _atomic_write(
        args.output_json,
        json.dumps(inventory, ensure_ascii=False, indent=2) + "\n",
    )
    _atomic_write(args.output_md, render_markdown(inventory))

    if not args.quiet:
        print(f"Skill inventory refreshed: {len(inventory['skills'])} skills")
        print(f"json: {args.output_json}")
        print(f"md: {args.output_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
