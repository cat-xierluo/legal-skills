#!/usr/bin/env python3
"""
Skill Manager - Record Management Module
管理 Skill 安装记录、版本追踪和更新检查
"""

import json
import os
import sys
import re
import subprocess
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

# 获取脚本所在目录
SCRIPT_DIR = Path(__file__).parent.resolve()
MANAGER_DIR = SCRIPT_DIR.parent
ASSETS_DIR = MANAGER_DIR / "assets"
# SKILL_MANAGER_REGISTRY 环境变量可覆盖（测试/非标准安装位置，与 relink-skill.py 一致）
REGISTRY_FILE = Path(os.environ.get("SKILL_MANAGER_REGISTRY") or (ASSETS_DIR / "skill-registry.json"))
EXAMPLE_FILE = ASSETS_DIR / "skill-registry.example.json"

# 确保 assets 目录存在
ASSETS_DIR.mkdir(exist_ok=True)


def get_current_timestamp():
    """获取当前时间戳 (ISO 8601 格式)"""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _migrate_entry(name: str, entry: dict) -> dict:
    """为旧条目填充缺失的新字段"""
    source = entry.get("source", "")
    if "install_type" not in entry:
        if "github.com" in source or ("/" in source and not source.startswith("/") and not source.startswith("~")):
            entry["install_type"] = "remote"
        else:
            entry["install_type"] = "local"
    if "install_commit" not in entry:
        entry["install_commit"] = None
    if "install_branch" not in entry:
        entry["install_branch"] = None
    if "remote_url" not in entry:
        entry["remote_url"] = None
    if "remote_subpath" not in entry:
        entry["remote_subpath"] = None
    if "last_check_at" not in entry:
        entry["last_check_at"] = None
    return entry


def load_registry() -> dict:
    """加载 Skill 注册表（自动迁移旧条目）"""
    if REGISTRY_FILE.exists():
        try:
            with open(REGISTRY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                registry = {k: _migrate_entry(k, v) for k, v in data.items() if not k.startswith('_')}
                return registry
        except (json.JSONDecodeError, IOError):
            pass

    # 如果注册表不存在，尝试从示例文件初始化
    if EXAMPLE_FILE.exists():
        try:
            with open(EXAMPLE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                registry = {k: _migrate_entry(k, v) for k, v in data.items() if not k.startswith('_')}
                if registry:
                    save_registry(registry)
                    return registry
        except (json.JSONDecodeError, IOError):
            pass

    return {}


def save_registry(registry: dict):
    """保存 Skill 注册表"""
    with open(REGISTRY_FILE, 'w', encoding='utf-8') as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)


def get_skill_version(skill_path: Path) -> Optional[str]:
    """从 SKILL.md 读取版本号"""
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        skill_md = skill_path / "skill.md"
    
    if skill_md.exists():
        try:
            content = skill_md.read_text(encoding='utf-8')
            # 匹配 version: "1.2.0" 或 version: "1.2.0"
            match = re.search(r'version:\s*["\']?(\d+\.\d+\.\d+)["\']?', content, re.IGNORECASE)
            if match:
                return match.group(1)
        except Exception:
            pass
    return None


def get_skill_info(skill_path: Path) -> dict:
    """获取 Skill 的详细信息"""
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        skill_md = skill_path / "skill.md"
    
    info = {
        "name": skill_path.name,
        "version": None,
        "description": None,
        "author": None,
        "homepage": None,
        "updated_at": None,
    }
    
    if skill_md.exists():
        try:
            content = skill_md.read_text(encoding='utf-8')
            
            # 提取 version
            match = re.search(r'version:\s*["\']?(\d+\.\d+\.\d+)["\']?', content, re.IGNORECASE)
            if match:
                info["version"] = match.group(1)
            
            # 提取 description
            match = re.search(r'description:\s*["\']([^"\']+)["\']', content, re.IGNORECASE)
            if match:
                info["description"] = match.group(1)
            
            # 提取 author
            match = re.search(r'author:\s*["\']([^"\']+)["\']', content, re.IGNORECASE)
            if match:
                info["author"] = match.group(1)
            
            # 提取 homepage
            match = re.search(r'homepage:\s*["\']([^"\']+)["\']', content, re.IGNORECASE)
            if match:
                info["homepage"] = match.group(1)
        except Exception:
            pass
    
    return info


def parse_github_url(url: str) -> Optional[tuple]:
    """解析 GitHub URL，返回 (owner, repo, subpath)

    支持格式:
    - https://github.com/owner/repo
    - https://github.com/owner/repo/tree/branch/path/to/skill
    - owner/repo
    - owner/repo/branch/path/to/skill
    """
    if not url:
        return None

    # 处理简写格式 owner/repo[/branch/path]
    if '/' in url and not url.startswith('http'):
        parts = url.split('/')
        if len(parts) >= 2:
            subpath = '/'.join(parts[2:]) if len(parts) > 2 else None
            return (parts[0], parts[1], subpath)
        return None

    # 处理完整 URL
    parsed = urlparse(url)
    if 'github.com' in parsed.netloc:
        path_parts = [p for p in parsed.path.split('/') if p]
        if len(path_parts) >= 2:
            owner = path_parts[0]
            repo = path_parts[1].replace('.git', '')
            # 处理 /tree/branch/subpath 格式
            if len(path_parts) >= 5 and path_parts[2] == 'tree':
                subpath = '/'.join(path_parts[4:])
                return (owner, repo, subpath if subpath else None)
            # 处理 /blob/branch/subpath 格式
            elif len(path_parts) >= 5 and path_parts[2] == 'blob':
                subpath = '/'.join(path_parts[4:])
                return (owner, repo, subpath if subpath else None)
            else:
                subpath = '/'.join(path_parts[2:]) if len(path_parts) > 2 else None
                return (owner, repo, subpath)

    return None


def get_raw_github_content(owner: str, repo: str, path: str = None, branch: str = "main") -> Optional[str]:
    """通过 raw.githubusercontent.com 获取 GitHub 文件内容"""
    try:
        if path:
            url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
        else:
            # 默认获取 SKILL.md
            url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/SKILL.md"
        
        import urllib.request
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read().decode('utf-8')
    except Exception:
        return None


def get_github_changelog(owner: str, repo: str, branch: str = "main", skill_path: str = None) -> Optional[str]:
    """获取 GitHub 仓库的 CHANGELOG 内容"""
    # 构建 CHANGELOG.md 的路径
    if skill_path:
        # 如果 skill_path 是目录，需要加上 CHANGELOG.md
        if not skill_path.endswith("CHANGELOG.md"):
            skill_path = f"{skill_path}/CHANGELOG.md"
    else:
        skill_path = "CHANGELOG.md"
    
    return get_raw_github_content(owner, repo, skill_path, branch)


def get_github_commits(owner: str, repo: str, branch: str = "main", skill_path: str = None, limit: int = 5) -> list:
    """获取 GitHub 仓库/文件的最近 commits"""
    try:
        # 构建 commits URL
        if skill_path:
            url = f"https://github.com/{owner}/{repo}/commits/{branch}/{skill_path}"
        else:
            url = f"https://github.com/{owner}/{repo}/commits/{branch}"

        html = fetch_webpage(url)
        if not html:
            return []

        commits = []

        # GitHub 在 <script type="application/json" data-target="react-app.embeddedData"> 中嵌入了 JSON
        json_pattern = re.compile(
            r'<script[^>]*data-target="react-app\.embeddedData"[^>]*>\s*(\{.*?\})\s*</script>',
            re.DOTALL
        )
        match = json_pattern.search(html)
        if match:
            try:
                payload = json.loads(match.group(1))
                for group in payload.get("payload", {}).get("commitGroups", []):
                    for c in group.get("commits", []):
                        commit = {
                            "sha": c.get("oid", "")[:7],
                            "time": c.get("committedDate", ""),
                            "message": c.get("shortMessage", ""),
                            "url": f"https://github.com/{owner}/{repo}/commit/{c.get('oid', '')[:7]}"
                        }
                        if commit["sha"] and commit["sha"] not in [x["sha"] for x in commits]:
                            commits.append(commit)
                            if len(commits) >= limit:
                                return commits
            except (json.JSONDecodeError, KeyError):
                pass

        return commits
    except Exception:
        return []


def get_github_skill_version(owner: str, repo: str, branch: str = "main", skill_path: str = None) -> Optional[tuple]:
    """获取远程 Skill 的版本号和最后更新时间"""
    # 构建 SKILL.md 的路径
    if skill_path:
        # 如果 skill_path 是目录，需要加上 SKILL.md
        if not skill_path.endswith("SKILL.md"):
            skill_path = f"{skill_path}/SKILL.md"
    else:
        skill_path = "SKILL.md"
    
    content = get_raw_github_content(owner, repo, skill_path, branch)
    if not content:
        return None, None
    
    version = None
    updated = None
    
    # 匹配 version
    match = re.search(r'version:\s*["\']?(\d+\.\d+\.\d+)["\']?', content, re.IGNORECASE)
    if match:
        version = match.group(1)
    
    # 尝试从原始 URL 获取最后更新
    # 注意：raw.githubusercontent.com 不提供修改时间，我们需要通过其他方式
    # 一种方式是检查 GitHub commits API，但用户说不使用 API
    # 另一种方式是在返回内容中标注获取时间
    
    return version, get_current_timestamp()


def fetch_webpage(url: str) -> Optional[str]:
    """获取网页内容"""
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode('utf-8', errors='ignore')
    except Exception:
        return None


def get_github_last_modified(owner: str, repo: str, skill_path: str = None, branch: str = "main") -> Optional[str]:
    """获取 GitHub 文件的最后修改时间（通过网页）"""
    # 构建文件的路径
    if skill_path:
        # 如果 skill_path 是目录，需要加上 SKILL.md
        if not skill_path.endswith("SKILL.md"):
            skill_path = f"{skill_path}/SKILL.md"
    else:
        skill_path = "SKILL.md"
    
    try:
        # GitHub 的 blob 页面有 relative-time 标签
        url = f"https://github.com/{owner}/{repo}/blob/{branch}/{skill_path}"
        html = fetch_webpage(url)
        
        if html:
            # 查找 <relative-time> 标签
            match = re.search(r'<relative-time[^>]*datetime="([^"]+)"', html)
            if match:
                return match.group(1)
            
            # 备用：查找 commit 信息
            match = re.search(r'data-pjax-date="([^"]+)"', html)
            if match:
                return match.group(1)
    except Exception:
        pass
    return None


def get_local_skill_info(skill_path: Path) -> dict:
    """获取本地已安装 Skill 的完整信息"""
    registry = load_registry()
    name = skill_path.name
    
    # 先从注册表获取基础信息
    base_info = registry.get(name, {})
    
    # 获取 SKILL.md 中的信息
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        skill_md = skill_path / "skill.md"
    
    if skill_md.exists():
        content = skill_md.read_text(encoding='utf-8')
        
        # 提取没有的信息
        if not base_info.get("description"):
            match = re.search(r'description:\s*["\']([^"\']+)["\']', content, re.IGNORECASE)
            if match:
                base_info["description"] = match.group(1)
        
        if not base_info.get("version"):
            match = re.search(r'version:\s*["\']?(\d+\.\d+\.\d+)["\']?', content, re.IGNORECASE)
            if match:
                base_info["version"] = match.group(1)
                base_info["current_version"] = match.group(1)
        
        if not base_info.get("homepage"):
            match = re.search(r'homepage:\s*["\']([^"\']+)["\']', content, re.IGNORECASE)
            if match:
                base_info["homepage"] = match.group(1)
    else:
        base_info["current_version"] = base_info.get("version")
    
    base_info["name"] = name
    base_info["local_path"] = str(skill_path)
    
    return base_info


def record_install(skill_name: str, source: str, skill_path: Path = None, action: str = "install",
                   install_type: str = None, install_commit: str = None,
                   install_branch: str = None, remote_url: str = None,
                   remote_subpath: str = None):
    """记录 Skill 安装/更新"""
    registry = load_registry()

    # 自动推断 install_type
    if not install_type:
        if source and ("github.com" in source or ("/" in source and not source.startswith("/") and not source.startswith("~"))):
            install_type = "remote"
        else:
            install_type = "local"

    info = {
        "name": skill_name,
        "source": source,
        "install_type": install_type,
        "installed_at": get_current_timestamp(),
        "last_updated": get_current_timestamp(),
        "installed_version": None,
        "current_version": None,
        "description": None,
        "homepage": None,
        "install_commit": install_commit,
        "install_branch": install_branch,
        "remote_url": remote_url or (source if install_type == "remote" else None),
        "remote_subpath": remote_subpath,
        "last_check_at": None,
    }
    
    # 如果有本地路径，读取 SKILL.md
    if skill_path and skill_path.exists():
        skill_info = get_skill_info(skill_path)
        info["installed_version"] = skill_info.get("version")
        info["current_version"] = skill_info.get("version")
        info["description"] = skill_info.get("description")
        info["homepage"] = skill_info.get("homepage")
    
    # 解析 GitHub 来源获取远程版本
    if source:
        gh_info = parse_github_url(source)
        if gh_info:
            owner, repo, subpath = gh_info
            remote_version, _ = get_github_skill_version(owner, repo, skill_path=subpath)
            if remote_version:
                info["latest_version"] = remote_version
                if not info["current_version"]:
                    info["current_version"] = remote_version
    
    # 保留已有 install_links（链接位置建档，供 relink-skill.py --from-registry 秒查），
    # 并登记本次安装位置（幂等去重）
    previous = registry.get(skill_name) or {}
    if isinstance(previous.get("install_links"), list):
        info["install_links"] = previous["install_links"]
    if skill_path:
        link_path = str(skill_path)
        if not any((i.get("path") if isinstance(i, dict) else i) == link_path
                   for i in info.get("install_links", [])):
            info.setdefault("install_links", []).append({
                "path": link_path, "target": source,
                "recorded_at": get_current_timestamp(), "via": "install"})

    # 更新或创建记录
    registry[skill_name] = info
    save_registry(registry)

    return info


def record_update(skill_name: str, old_version: str = None, new_version: str = None):
    """记录 Skill 更新"""
    registry = load_registry()
    
    if skill_name in registry:
        registry[skill_name]["last_updated"] = get_current_timestamp()
        if new_version:
            registry[skill_name]["current_version"] = new_version
            registry[skill_name]["installed_version"] = old_version or registry[skill_name].get("installed_version")
        save_registry(registry)
    
    return registry.get(skill_name)


def check_updates_for_skill(skill_name: str) -> dict:
    """检查单个 Skill 的更新状态"""
    registry = load_registry()
    skill_info = registry.get(skill_name, {})

    source = skill_info.get("source")
    current_version = skill_info.get("current_version")
    installed_at = skill_info.get("installed_at")

    result = {
        "name": skill_name,
        "source": source,
        "current_version": current_version,
        "latest_version": current_version,
        "has_update": False,
        "changelog": None,
        "commits": [],
        "last_modified": None,
        "error": None,
    }

    if not source:
        result["error"] = "无来源信息"
        return result

    # 解析 GitHub 来源
    # 优先使用 remote_subpath（精确到 Skill 子目录），其次解析 remote_url
    remote_url = skill_info.get("remote_url") or source
    remote_subpath = skill_info.get("remote_subpath")

    gh_info = parse_github_url(remote_url)
    if not gh_info:
        result["error"] = "无法解析来源"
        return result

    owner, repo, url_subpath = gh_info
    # 使用精确的 subpath：remote_subpath > URL 解析 > None
    subpath = remote_subpath or url_subpath

    # 策略 1: 有版本号 → 比较版本
    remote_version, fetch_time = get_github_skill_version(owner, repo, skill_path=subpath)
    if remote_version and current_version:
        result["latest_version"] = remote_version
        result["has_update"] = remote_version != current_version

    # 策略 2: 无版本号 → 检查最近 commits 是否有新于安装时间的
    if not result["has_update"] and not current_version:
        commits = get_github_commits(owner, repo, skill_path=subpath)
        if commits and installed_at:
            try:
                installed_dt = datetime.fromisoformat(installed_at)
                for c in commits:
                    commit_time = c.get("time", "")
                    if commit_time:
                        commit_dt = datetime.fromisoformat(commit_time.replace("Z", "+00:00"))
                        # commit 时间晚于安装时间 → 有更新
                        if commit_dt > installed_dt:
                            result["has_update"] = True
                            break
            except (ValueError, TypeError):
                # 时间解析失败，有 commits 就认为可能有更新
                if commits:
                    result["has_update"] = True
        if commits:
            result["commits"] = commits

    # 补充信息：changelog 和最后修改时间
    changelog = get_github_changelog(owner, repo, skill_path=subpath)
    if changelog:
        result["changelog"] = changelog

    # 如果策略 1 没获取到 commits（有版本号时也要获取 commits 作为补充信息）
    if not result["commits"]:
        commits = get_github_commits(owner, repo, skill_path=subpath)
        if commits:
            result["commits"] = commits

    last_modified = get_github_last_modified(owner, repo, skill_path=subpath)
    if last_modified:
        result["last_modified"] = last_modified

    # 更新 last_check_at
    now = get_current_timestamp()
    reg = load_registry()
    if skill_name in reg:
        reg[skill_name]["last_check_at"] = now
        if remote_version:
            reg[skill_name]["latest_version"] = remote_version
        save_registry(reg)
    result["last_check_at"] = now

    return result


def check_all_updates() -> list:
    """检查所有已安装 Skill 的更新状态（仅远程安装的 Skill 检查远程更新）"""
    registry = load_registry()
    results = []

    for skill_name, entry in registry.items():
        install_type = entry.get("install_type", "local")
        source = entry.get("source", "")
        is_remote = install_type == "remote" or "github.com" in source

        if is_remote:
            result = check_updates_for_skill(skill_name)
            results.append(result)
        else:
            # 本地 Skill（符号链接）自动同步，无需远程检查
            results.append({
                "name": skill_name,
                "source": source,
                "current_version": entry.get("current_version"),
                "latest_version": entry.get("current_version"),
                "has_update": False,
                "changelog": None,
                "commits": [],
                "last_modified": None,
                "error": None,
                "skipped": True,
            })

    return results


DEFAULT_STALE_THRESHOLD_DAYS = 7


def check_stale_remote_skills(threshold_days: int = DEFAULT_STALE_THRESHOLD_DAYS) -> list:
    """检查超过阈值的远程 Skill 更新状态"""
    registry = load_registry()
    results = []
    now = datetime.now().astimezone()

    for skill_name, entry in registry.items():
        source = entry.get("source", "")
        install_type = entry.get("install_type", "local")
        is_remote = install_type == "remote" or "github.com" in source
        if not is_remote:
            continue

        last_check = entry.get("last_check_at")
        if last_check:
            try:
                last_check_dt = datetime.fromisoformat(last_check)
                days_since = (now - last_check_dt).days
                if days_since < threshold_days:
                    continue
            except (ValueError, TypeError):
                pass

        result = check_updates_for_skill(skill_name)
        results.append(result)

    return results


def summarize_updates(result: dict) -> str:
    """将更新检测结果总结为一段简明的更新摘要"""
    commits = result.get("commits", [])
    changelog = result.get("changelog")
    current = result.get("current_version")
    latest = result.get("latest_version")

    parts = []

    # 版本变化
    if current and latest and current != latest:
        parts.append(f"版本 {current} → {latest}")

    # 从 changelog 提取最新版本的更新说明
    changelog_extracted = False
    if changelog:
        sections = re.split(r'^##\s', changelog, maxsplit=2)
        if len(sections) > 1:
            latest_section = sections[1]
            summary_lines = []
            for line in latest_section.split('\n'):
                line = line.strip().lstrip('- ').strip()
                if line and not line.startswith('#') and not line.startswith('['):
                    summary_lines.append(line)
                    if len(summary_lines) >= 3:
                        break
            if summary_lines:
                parts.append('；'.join(summary_lines))
                changelog_extracted = True

    # 从 commits 生成摘要（仅在 changelog 未提取到内容时）
    if commits and not changelog_extracted:
        summaries = []
        for c in commits[:5]:
            msg = c.get("message", "")
            if not msg:
                continue
            if msg.startswith("Merge pull request"):
                continue
            msg = msg.split('\n')[0]
            msg = re.sub(r'^(feat|fix|docs|chore|refactor|perf|test|ci|build|style)(\([^)]*\))?:\s*', '', msg)
            if msg:
                summaries.append(msg[:50])
        if summaries:
            parts.append('；'.join(summaries))

    # 兜底：只说有多少新 commit
    if not parts and commits:
        parts.append(f"安装后有 {len(commits)} 个新提交")

    return '，'.join(parts) if parts else "检测到远程更新"


def format_recommendation_report(results: list) -> str:
    """格式化更新推荐报告（仅对有更新的 skill 输出）"""
    has_update = [r for r in results if r.get("has_update")]
    if not has_update:
        return ""

    lines = []
    lines.append("=" * 60)
    lines.append("Skill 更新推荐")
    lines.append("=" * 60)
    lines.append("")

    for r in has_update:
        lines.append(f"  * {r['name']}")
        # 更新摘要
        summary = summarize_updates(r)
        lines.append(f"    {summary}")
        if r.get("source"):
            lines.append(f"    更新: skill-manager install {r['source']}")
        lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)


def format_version_list(updates: list) -> str:
    """格式化版本列表为可读文本"""
    if not updates:
        return "没有已安装的 Skills\n"
    
    lines = []
    lines.append("=" * 60)
    lines.append("🔍 Skill 更新检查")
    lines.append("=" * 60)
    lines.append("")
    
    # 按状态分组
    has_update = [u for u in updates if u.get("has_update")]
    up_to_date = [u for u in updates if not u.get("has_update") and not u.get("error") and not u.get("skipped")]
    local_skills = [u for u in updates if u.get("skipped")]
    errors = [u for u in updates if u.get("error")]
    
    if has_update:
        lines.append("📦 有可用更新:")
        lines.append("-" * 40)
        for u in has_update:
            lines.append(f"  • {u['name']}")
            summary = summarize_updates(u)
            lines.append(f"    {summary}")
            lines.append("")
    
    if up_to_date:
        lines.append("✅ 已是最新:")
        lines.append("-" * 40)
        for u in up_to_date:
            lines.append(f"  • {u['name']} (v{u.get('current_version', '?')})")
        lines.append("")
    
    if errors:
        lines.append("⚠️  检查失败:")
        lines.append("-" * 40)
        for u in errors:
            lines.append(f"  • {u['name']}: {u.get('error')}")
        lines.append("")

    if local_skills:
        lines.append("🔗 本地安装（自动同步，无需检查）:")
        lines.append("-" * 40)
        for u in local_skills:
            ver = u.get('current_version', '?')
            lines.append(f"  • {u['name']}" + (f" (v{ver})" if ver else ""))
        lines.append("")

    lines.append("=" * 60)
    
    return "\n".join(lines)


def format_install_record(info: dict) -> str:
    """格式化安装记录"""
    lines = []
    lines.append("=" * 40)
    lines.append("📦 Skill 安装记录")
    lines.append("=" * 40)
    lines.append(f"  名称: {info.get('name', '未知')}")
    lines.append(f"  来源: {info.get('source', '未知')}")
    lines.append(f"  版本: {info.get('current_version', '未知')}")
    lines.append(f"  时间: {info.get('installed_at', '未知')}")
    if info.get("description"):
        lines.append(f"  描述: {info['description']}")
    lines.append("=" * 40)
    return "\n".join(lines)


def main():
    """主入口"""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  record.py install <skill_name> <source> [--path <path>] [--install-type <type>] [--install-commit <hash>] [--install-branch <branch>] [--remote-url <url>]")
        print("  record.py check <skill_name>")
        print("  record.py check-all")
        print("  record.py auto-check [--threshold <days>]")
        print("  record.py list")
        print("  record.py update <skill_name> [--from <version>] [--to <version>]")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "install":
        # record.py install <skill_name> <source> [--path <path>] [--install-type <type>] [--install-commit <hash>] [--install-branch <branch>] [--remote-url <url>] [--remote-subpath <path>]
        skill_name = sys.argv[2] if len(sys.argv) > 2 else None
        source = sys.argv[3] if len(sys.argv) > 3 else None
        path = None
        install_type = None
        install_commit = None
        install_branch = None
        remote_url = None
        remote_subpath = None

        for i, arg in enumerate(sys.argv):
            if arg == "--path" and len(sys.argv) > i + 1:
                path = Path(sys.argv[i + 1])
            elif arg == "--install-type" and len(sys.argv) > i + 1:
                install_type = sys.argv[i + 1]
            elif arg == "--install-commit" and len(sys.argv) > i + 1:
                install_commit = sys.argv[i + 1]
            elif arg == "--install-branch" and len(sys.argv) > i + 1:
                install_branch = sys.argv[i + 1]
            elif arg == "--remote-url" and len(sys.argv) > i + 1:
                remote_url = sys.argv[i + 1]
            elif arg == "--remote-subpath" and len(sys.argv) > i + 1:
                remote_subpath = sys.argv[i + 1]

        if not skill_name or not source:
            print("❌ 错误: 请提供 skill_name 和 source")
            sys.exit(1)

        info = record_install(skill_name, source, path,
                              install_type=install_type,
                              install_commit=install_commit,
                              install_branch=install_branch,
                              remote_url=remote_url,
                              remote_subpath=remote_subpath)
        print(format_install_record(info))
    
    elif command == "auto-check":
        threshold = DEFAULT_STALE_THRESHOLD_DAYS
        for i, arg in enumerate(sys.argv):
            if arg == "--threshold" and len(sys.argv) > i + 1:
                threshold = int(sys.argv[i + 1])
        results = check_stale_remote_skills(threshold_days=threshold)
        report = format_recommendation_report(results)
        if report:
            print(report)

    elif command == "check":
        # record.py check <skill_name>
        skill_name = sys.argv[2] if len(sys.argv) > 2 else None
        if not skill_name:
            print("❌ 错误: 请提供 skill_name")
            sys.exit(1)
        
        result = check_updates_for_skill(skill_name)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    elif command == "check-all":
        results = check_all_updates()
        print(format_version_list(results))
    
    elif command == "list":
        registry = load_registry()
        if not registry:
            print("📭 暂无安装记录")
        else:
            for name, info in registry.items():
                print(f"\n📦 {name}")
                print(f"   版本: {info.get('current_version', '未知')}")
                print(f"   来源: {info.get('source', '未知')}")
                print(f"   类型: {info.get('install_type', '未知')}")
                print(f"   安装时间: {info.get('installed_at', '未知')}")
                if info.get("install_commit"):
                    print(f"   安装 Commit: {info['install_commit']}")
                if info.get("install_branch"):
                    print(f"   安装 Branch: {info['install_branch']}")
                if info.get("last_check_at"):
                    print(f"   上次检查: {info['last_check_at']}")
                if info.get("description"):
                    print(f"   描述: {info['description']}")
    
    elif command == "update":
        # record.py update <skill_name> [--from <version>] [--to <version>]
        skill_name = sys.argv[2] if len(sys.argv) > 2 else None
        old_version = None
        new_version = None
        
        for i, arg in enumerate(sys.argv):
            if arg == "--from" and len(sys.argv) > i + 1:
                old_version = sys.argv[i + 1]
            if arg == "--to" and len(sys.argv) > i + 1:
                new_version = sys.argv[i + 1]
        
        if not skill_name:
            print("❌ 错误: 请提供 skill_name")
            sys.exit(1)
        
        info = record_update(skill_name, old_version, new_version)
        if info:
            print(f"✅ 已更新记录: {skill_name}")
            if old_version and new_version:
                print(f"   {old_version} → {new_version}")
        else:
            print(f"⚠️ 未找到记录: {skill_name}")
    
    else:
        print(f"❌ 未知命令: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
