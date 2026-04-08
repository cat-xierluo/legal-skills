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
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

# 获取脚本所在目录
SCRIPT_DIR = Path(__file__).parent.resolve()
MANAGER_DIR = SCRIPT_DIR.parent
ASSETS_DIR = MANAGER_DIR / "assets"
REGISTRY_FILE = ASSETS_DIR / "skill-registry.json"
EXAMPLE_FILE = ASSETS_DIR / "skill-registry.example.json"

# 确保 assets 目录存在
ASSETS_DIR.mkdir(exist_ok=True)


def get_local_timezone():
    """获取当前时区偏移"""
    now = datetime.now()
    offset = now.strftime('%z')
    # 转换为 +08:00 格式
    if offset:
        if len(offset) == 5:
            return f"{offset[:3]}:{offset[3:]}"
    return "+08:00"


def get_current_timestamp():
    """获取当前时间戳 (ISO 8601 格式)"""
    tz = get_local_timezone()
    return datetime.now(timezone.utc).strftime(f'%Y-%m-%dT%H:%M:%S{tz}')


def load_registry() -> dict:
    """加载 Skill 注册表"""
    if REGISTRY_FILE.exists():
        try:
            with open(REGISTRY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 过滤掉 _note 等元数据字段
                return {k: v for k, v in data.items() if not k.startswith('_')}
        except (json.JSONDecodeError, IOError):
            pass
    
    # 如果注册表不存在，尝试从示例文件初始化
    if EXAMPLE_FILE.exists():
        try:
            with open(EXAMPLE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 过滤掉 _note 等元数据字段
                registry = {k: v for k, v in data.items() if not k.startswith('_')}
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
    """解析 GitHub URL，返回 (owner, repo, path)"""
    if not url:
        return None
    
    # 处理简写格式 owner/repo
    if '/' in url and not url.startswith('http'):
        parts = url.split('/')
        if len(parts) >= 2:
            return (parts[0], parts[1], None)
        return None
    
    # 处理完整 URL
    parsed = urlparse(url)
    if 'github.com' in parsed.netloc:
        path_parts = [p for p in parsed.path.split('/') if p]
        if len(path_parts) >= 2:
            owner = path_parts[0]
            repo = path_parts[1].replace('.git', '')
            path = '/'.join(path_parts[2:]) if len(path_parts) > 2 else None
            return (owner, repo, path)
    
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
        
        # 解析 commit 条目 - GitHub 的 HTML 结构
        # 查找 commit 列表中的每个条目
        commit_pattern = re.compile(
            r'<a[^>]*href="/' + re.escape(owner) + r'/' + re.escape(repo) + r'/commit/([^"]+)"[^>]*>' +
            r'[^<]*<svg[^>]*>[^<]*</svg>[^<]*<time[^>]*datetime="([^"]+)"',
            re.DOTALL
        )
        
        for match in commit_pattern.finditer(html):
            commit_sha = match.group(1)[:7]  # 取前7位
            commit_time = match.group(2)
            commits.append({
                "sha": commit_sha,
                "time": commit_time,
                "url": f"https://github.com/{owner}/{repo}/commit/{commit_sha}"
            })
            if len(commits) >= limit:
                break
        
        # 如果上面没匹配到，尝试另一种模式
        if not commits:
            # 匹配 time 标签和 commit 标题
            time_pattern = re.compile(r'<time[^>]*datetime="([^"]+)"[^>]*>.*?</time>.*?<a[^>]*class="[^*"]*message[^"]*"[^>]*>([^<]+)</a>', re.DOTALL)
            for match in time_pattern.finditer(html):
                commit_time = match.group(1)
                commit_msg = match.group(2).strip()
                commits.append({
                    "sha": "unknown",
                    "time": commit_time,
                    "message": commit_msg,
                    "url": url
                })
                if len(commits) >= limit:
                    break
        
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


def record_install(skill_name: str, source: str, skill_path: Path = None, action: str = "install"):
    """记录 Skill 安装/更新"""
    registry = load_registry()
    
    info = {
        "name": skill_name,
        "source": source,
        "installed_at": get_current_timestamp(),
        "last_updated": get_current_timestamp(),
        "installed_version": None,
        "current_version": None,
        "description": None,
        "homepage": None,
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
    gh_info = parse_github_url(source)
    if not gh_info:
        result["error"] = "无法解析来源"
        return result
    
    owner, repo, subpath = gh_info
    
    # 获取远程版本
    remote_version, fetch_time = get_github_skill_version(owner, repo, skill_path=subpath)
    if remote_version:
        result["latest_version"] = remote_version
        result["has_update"] = remote_version != current_version
    
    # 尝试获取 changelog
    changelog = get_github_changelog(owner, repo, skill_path=subpath)
    if changelog:
        result["changelog"] = changelog
    
    # 获取最近的 commits（如果没有 changelog 或作为补充）
    commits = get_github_commits(owner, repo, skill_path=subpath)
    if commits:
        result["commits"] = commits
    
    # 获取最后修改时间
    last_modified = get_github_last_modified(owner, repo, skill_path=subpath)
    if last_modified:
        result["last_modified"] = last_modified
    
    return result


def check_all_updates() -> list:
    """检查所有已安装 Skill 的更新状态"""
    registry = load_registry()
    results = []
    
    for skill_name in registry:
        result = check_updates_for_skill(skill_name)
        results.append(result)
    
    return results


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
    up_to_date = [u for u in updates if not u.get("has_update") and not u.get("error")]
    errors = [u for u in updates if u.get("error")]
    
    if has_update:
        lines.append("📦 有可用更新:")
        lines.append("-" * 40)
        for u in has_update:
            lines.append(f"  • {u['name']}")
            lines.append(f"    当前: {u.get('current_version', '未知')}")
            lines.append(f"    最新: {u.get('latest_version', '未知')}")
            if u.get("last_modified"):
                lines.append(f"    更新于: {u['last_modified'][:10]}")
            
            # 显示 changelog 或 commits
            if u.get("changelog"):
                # 截取 changelog 前 200 字符
                changelog_preview = u["changelog"][:200].split('\n')[0]
                lines.append(f"    更新内容: {changelog_preview}...")
            elif u.get("commits"):
                # 显示最近的 commits
                lines.append(f"    最近更新:")
                for i, commit in enumerate(u["commits"][:3]):
                    msg = commit.get("message", commit.get("sha", ""))
                    lines.append(f"      {i+1}. {msg[:60]}{'...' if len(msg) > 60 else ''}")
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
        print("  record.py install <skill_name> <source> [--path <path>]")
        print("  record.py check <skill_name>")
        print("  record.py check-all")
        print("  record.py list")
        print("  record.py update <skill_name> [--from <version>] [--to <version>]")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "install":
        # record.py install <skill_name> <source> [--path <path>]
        skill_name = sys.argv[2] if len(sys.argv) > 2 else None
        source = sys.argv[3] if len(sys.argv) > 3 else None
        path = None
        
        for i, arg in enumerate(sys.argv):
            if arg == "--path" and len(sys.argv) > i + 1:
                path = Path(sys.argv[i + 1])
        
        if not skill_name or not source:
            print("❌ 错误: 请提供 skill_name 和 source")
            sys.exit(1)
        
        info = record_install(skill_name, source, path)
        print(format_install_record(info))
    
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
                print(f"   安装时间: {info.get('installed_at', '未知')}")
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
