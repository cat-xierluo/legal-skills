#!/usr/bin/env python3
"""generate-release-notes.py — 从 README 自动生成结构化的 GitHub Release Notes

设计:通用模板 + 项目级个性化配置(从 projects.yaml 读)

用法:
  python3 generate-release-notes.py <repo> <tag> [project_key] [top_n] [readme] [output]

参数:
  repo         owner/repo(如 cat-xierluo/legal-skills)
  tag          本次 release 的 tag
  project_key  projects.yaml 里的项目 key(用于读 notes: 个性化配置);省略则用纯默认
  top_n        提取最近更新的子项目数量(默认 5)
  readme_path  README 路径(默认 ./README.md)
  output_path  输出文件路径(默认 .release-notes.md,gitignored)

个性化配置(在 projects.yaml 项目的 `notes:` 字段下):
  project_label:    标题用名(默认用 repo 最后一段)
  intro_template:   简介模板,支持 {total} {label} 占位符
  recent:
    source_marker:  README 里的章节标题(默认 "🆕 最近更新的 Skill")
    top_n:          默认 5
  install:
    single_label:   "下载某个 skill" / "下载某个 package" 等子项目单元名
    full_clone_prompt: 整仓克隆的 Agent 提示词模板,支持 {repo} {label}
    single_note:    单 zip 下载说明模板,支持 {label} 占位符

行为:
  1. 从 projects.yaml 读项目级 notes: 配置(如有)
  2. 从 README 提取最近更新表格(按 source_marker 定位)
  3. 拼装结构化 release notes

依赖:仅 Python 3 标准库(解析 YAML 用内置正则简化,如需完整 YAML 可加 PyYAML)。
"""
import os
import re
import subprocess
import sys
from pathlib import Path


def _parse_scalar(s: str):
    """解析标量值:去引号、试转 int"""
    s = s.strip().strip('"').strip("'")
    try:
        return int(s)
    except ValueError:
        return s


def _parse_yaml_block(text: str, start_key: str, parent_indent: int) -> dict:
    """从 text 中提取 key: 后的 block(支持 1 层嵌套)

    例如对 start_key="notes", parent_indent=2:
      找以 `  notes:` 开头(2 缩进)的行
      解析其下属所有内容(直到缩进回到 <= 2 或遇到下一个 2 缩进的同级 key)
    返回:key → value/scalar 或 key → {subkey: ...}

    支持的语法:
      key: value          → 标量
      key:                → 嵌套 dict 开始
        subkey: value
        subkey:
          deeper: ...      (不支持,忽略)
    """
    lines = text.split("\n")
    n = len(lines)

    # 1) 找到 start_key 起始行
    start_idx = -1
    start_line_indent = -1
    for i, line in enumerate(lines):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        content = line.lstrip()
        if indent == parent_indent and content == f"{start_key}:":
            start_idx = i
            start_line_indent = indent
            break

    if start_idx == -1:
        return {}

    # 2) 从下一行开始解析,直到缩进 <= start_line_indent
    block_indent = start_line_indent + 2  # 直接子字段的缩进
    result: dict = {}
    current_subkey: str | None = None
    current_subkey_indent: int = -1

    for i in range(start_idx + 1, len(lines)):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        content = line.lstrip()

        # 缩进回到父级或更浅 → block 结束
        if indent <= start_line_indent:
            break

        # 缩进等于 block_indent(直接子字段)
        if indent == block_indent:
            if ":" not in content:
                continue
            key, _, value = content.partition(":")
            key = key.strip()
            value = value.strip()
            if value:  # key: value(标量)
                result[key] = _parse_scalar(value)
                current_subkey = None
            else:  # key: (嵌套 dict 起始)
                current_subkey = key
                result[key] = {}
                current_subkey_indent = indent
        # 缩进更深 → 是 current_subkey 的子字段
        elif current_subkey and indent == current_subkey_indent + 2:
            if ":" not in content:
                continue
            key, _, value = content.partition(":")
            key = key.strip()
            value = value.strip()
            if value:
                if not isinstance(result.get(current_subkey), dict):
                    result[current_subkey] = {}
                result[current_subkey][key] = _parse_scalar(value)
        # 缩进更深但不是 current_subkey 的子字段 → 忽略
        # 缩进比 block_indent 浅但 > start_line_indent → 不应出现,忽略

    return result


def load_project_notes(projects_yaml: Path, project_key: str) -> dict:
    """从 projects.yaml 读指定 project_key 的 notes: 配置

    返回该项目的 notes 字段(dict),未找到返回空 dict。
    """
    if not projects_yaml.is_file():
        return {}

    text = projects_yaml.read_text()
    # 1) 找到 project_key 顶层块(缩进 0)
    project_block = _parse_yaml_block(text, project_key, parent_indent=0)
    if not project_block:
        return {}

    # 2) project_block 是个 dict,从中取 notes 子字段
    # 但 _parse_yaml_block 不会返回嵌套结构(它只解析一层嵌套),
    # 所以我们重新调用 _parse_yaml_block 解析 notes: 这一层
    # 找到 project_key 块的文本范围
    lines = text.split("\n")
    start = -1
    start_indent = -1
    for i, line in enumerate(lines):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        content = line.lstrip()
        if indent == 0 and content == f"{project_key}:":
            start = i
            start_indent = 0
            break
    if start == -1:
        return {}

    # 提取 project_key 块文本
    end = len(lines)
    for i in range(start + 1, len(lines)):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if indent == 0:
            end = i
            break
    block_text = "\n".join(lines[start:end])

    # 解析 notes: 子块(在 project_key 块内,缩进 2)
    return _parse_yaml_block(block_text, "notes", parent_indent=2)


def extract_recent_updates(readme_text: str, source_marker: str = "🆕 最近更新的 Skill",
                            top_n: int = 5) -> list[dict]:
    """从 README 的指定章节表格提取 top_n 条"""
    # 转义 marker 用于正则(emoji 等特殊字符需要处理)
    escaped = re.escape(source_marker)
    m = re.search(
        rf"{escaped}.*?\n(.*?)(?=</details>|## )",
        readme_text, re.DOTALL,
    )
    if not m:
        return []
    table = m.group(1)

    rows = []
    for line in table.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        # 跳过分隔行(---|---)和表头行
        if re.match(r"^\|[\s\-|:]+\|$", line):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 5:
            continue
        date, kind, skill_cell, version, summary = cells[:5]
        # 跳过表头(列名 "日期"/"Skill" 出现)
        if date == "日期" or skill_cell == "Skill":
            continue
        # 提取 skill 名称(去掉 [name](path) 格式的链接)
        skill_match = re.search(r"\[([^\]]+)\]", skill_cell)
        skill = skill_match.group(1) if skill_match else skill_cell
        rows.append({
            "date": date,
            "kind": kind,
            "skill": skill,
            "version": version,
            "summary": summary,
        })
    return rows[:top_n]


def extract_skill_count(readme_text: str) -> int:
    """从 README 的 badge 提取 skill 总数"""
    m = re.search(r"Skills-(\d+)", readme_text)
    return int(m.group(1)) if m else 0


def render_body(
    repo: str,
    tag: str,
    recent: list[dict],
    skill_count: int,
    notes_cfg: dict | None = None,
) -> str:
    """生成 release notes 主体。

    notes_cfg(从 projects.yaml 读的项目 notes 块):
      - project_label: 标题用名
      - intro_template: 简介模板
      - recent.source_marker: 表格章节标题
      - recent.top_n: 数量
      - install.single_label: "skill"/"package" 等
      - install.full_clone_prompt: 整仓克隆提示词模板
      - install.single_note: 单 zip 说明
    """
    notes_cfg = notes_cfg or {}
    n = len(recent)
    total = skill_count or n
    label = notes_cfg.get("project_label") or repo.split("/")[-1]

    # 简介(支持项目级模板覆盖)
    install_cfg = notes_cfg.get("install", {}) if isinstance(notes_cfg.get("install"), dict) else {}
    single_label = install_cfg.get("single_label", "子项目")
    intro_template = notes_cfg.get("intro_template")
    if intro_template:
        # 用 .format() 而非 f-string,因为模板里可能含 {total} {label} 等占位符
        try:
            intro = intro_template.format(total=total, label=label)
        except KeyError:
            intro = intro_template  # 模板含未知占位符时,原样使用
    else:
        intro = f"本版包含 **{total} 个** {single_label}的最新 zip。"

    lines: list[str] = []
    lines.append(f"## {label} 本次发布（{tag}）")
    lines.append("")
    lines.append(intro)
    lines.append("")

    if recent:
        lines.append(f"## 最近更新要点（最近 {n} 项）")
        lines.append("")
        lines.append("| 日期 | 子项目 | 版本 | 更新要点 |")
        lines.append("|------|-------|------|---------|")
        for r in recent:
            summary = r["summary"]
            if len(summary) > 80:
                summary = summary[:77] + "..."
            lines.append(
                f"| {r['date']} | **{r['skill']}** | {r['version']} | {summary} |"
            )
        lines.append("")

    # 安装方法(支持项目级模板)
    lines.append("## 安装方法")
    lines.append("")
    lines.append(f"### 整仓克隆（适合开发）")
    lines.append("")
    lines.append("将以下内容复制到你的 Agent 平台：")
    lines.append("")
    prompt = install_cfg.get("full_clone_prompt")
    if prompt:
        # 支持 {repo} {repo_url} {label} 占位符
        prompt = prompt.format(repo=repo, repo_url=f"https://github.com/{repo}", label=label)
    else:
        prompt = f"请帮我从 GitHub 安装：https://github.com/{repo}"
    lines.append(f"> {prompt}")
    lines.append("")

    lines.append(f"### 单独下载某个 {single_label}（推荐，无需 Git）")
    lines.append("")
    lines.append(
        f"1. 进入 [GitHub Releases](https://github.com/{repo}/releases/tag/{tag})"
    )
    lines.append("2. 在下方 Assets 中找到需要的 zip，点击下载")
    note = install_cfg.get("single_note") or f"3. 解压后直接得到 `<name>/` 文件夹，复制到 Agent 的目标目录即可"
    lines.append(note)
    lines.append("")
    lines.append(
        f"**下载链接规则**:`releases/latest/download/<name>-<semver>.zip` "
        "会始终指向最新 release 的对应 zip，无需手动查找版本号。"
    )
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        f"📖 完整列表与说明:https://github.com/{repo}/blob/{tag}/README.md"
    )

    return "\n".join(lines) + "\n"


def main() -> int:
    if len(sys.argv) < 3:
        print(
            "用法:python3 generate-release-notes.py <owner/repo> <tag> [project_key] [top_n] [readme] [output]",
            file=sys.stderr,
        )
        return 1

    repo = sys.argv[1]
    tag = sys.argv[2]
    project_key = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else ""
    top_n_override = int(sys.argv[4]) if len(sys.argv) > 4 and sys.argv[4] else None
    readme_path = Path(sys.argv[5]) if len(sys.argv) > 5 else Path("README.md")
    output_path = Path(sys.argv[6]) if len(sys.argv) > 6 else Path(".release-notes.md")

    if not readme_path.is_file():
        print(f"ERROR: README 不存在:{readme_path}", file=sys.stderr)
        return 1

    # 加载项目 notes 配置
    notes_cfg: dict = {}
    if project_key:
        projects_yaml = Path(os.environ.get("PROJECTS_YAML", "skills/release-workflow/config/projects.yaml"))
        notes_cfg = load_project_notes(projects_yaml, project_key)

    top_n = top_n_override or notes_cfg.get("recent", {}).get("top_n", 5)
    recent_cfg = notes_cfg.get("recent", {}) if isinstance(notes_cfg.get("recent"), dict) else {}
    source_marker = recent_cfg.get("source_marker", "🆕 最近更新的 Skill")

    readme_text = readme_path.read_text()
    recent = extract_recent_updates(readme_text, source_marker, top_n)
    skill_count = extract_skill_count(readme_text)
    body = render_body(repo, tag, recent, skill_count, notes_cfg)

    output_path.write_text(body)
    print(f"✅ release notes 已生成:{output_path} (top {len(recent)} 条最近更新, project={project_key or '(default)'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())