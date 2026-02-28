"""
GitHub Star 追踪器 - 核心分析模块
支持更新检测、版本追踪、活跃度分析、分类和标签管理
"""

import os
import json
import yaml
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set
from pathlib import Path


class StarTracker:
    """GitHub Star 更新追踪器"""

    API_BASE = "https://api.github.com"
    # 使用项目目录内的 output/ 目录（自包含项目原则）
    CACHE_DIR = Path(__file__).parent.parent / "output"
    CONFIG_DIR = CACHE_DIR  # 配置文件目录

    # 配置文件路径
    CATEGORIES_FILE = CONFIG_DIR / "categories.yaml"
    TAGS_FILE = CONFIG_DIR / "tags.json"
    SETTINGS_FILE = CONFIG_DIR / "user_settings.json"

    def __init__(self, github_token: Optional[str] = None):
        self.github_token = github_token or os.getenv("GITHUB_PAT")
        self.user = None
        self._auth_username = None
        self.headers = {"Accept": "application/vnd.github.v3+json"}
        if self.github_token:
            self.headers["Authorization"] = f"token {self.github_token}"

        # 确保目录存在
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        # 加载配置文件
        self.categories = self._load_categories()
        self.tags = self._load_tags()
        self.settings = self._load_settings()

    def _load_categories(self) -> List[Dict]:
        """加载分类配置"""
        if self.CATEGORIES_FILE.exists():
            try:
                with open(self.CATEGORIES_FILE, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f)
            except Exception:
                pass
        # 返回默认分类
        return self._get_default_categories()

    def _load_tags(self) -> Dict:
        """加载标签配置"""
        if self.TAGS_FILE.exists():
            try:
                with open(self.TAGS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {"version": "1.0", "tags": [], "tag_aliases": {}}

    def _load_settings(self) -> Dict:
        """加载用户设置"""
        if self.SETTINGS_FILE.exists():
            try:
                with open(self.SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _get_default_categories(self) -> List[Dict]:
        """获取默认分类列表"""
        return [
            {"id": "ai", "name": "AI/机器学习", "icon": "🤖", "color": "#22c55e",
             "keywords": ["ai", "llm", "agent", "claude", "gpt"]},
            {"id": "web", "name": "Web应用", "icon": "🌐", "color": "#3b82f6",
             "keywords": ["web", "frontend", "react"]},
            {"id": "desktop", "name": "桌面应用", "icon": "💻", "color": "#6b7280",
             "keywords": ["desktop", "electron"]},
            {"id": "mobile", "name": "移动应用", "icon": "📱", "color": "#f59e0b",
             "keywords": ["mobile", "android"]},
            {"id": "devtools", "name": "开发工具", "icon": "🔧", "color": "#00add8",
             "keywords": ["cli", "tool", "dev"]},
            {"id": "productivity", "name": "效率工具", "icon": "⚡", "color": "#f1c40f",
             "keywords": ["productivity"]},
            {"id": "education", "name": "教育学习", "icon": "📚", "color": "#3b82f6",
             "keywords": ["education", "docs"]},
            {"id": "reading", "name": "阅读收藏", "icon": "📖", "color": "#6366f1",
             "keywords": ["reading", "bookmark", "later"]},
        ]

    def save_tag(self, tag_name: str, color: str = None) -> bool:
        """保存新标签"""
        tags_data = self._load_tags()
        if tag_name not in tags_data.get("tags", []):
            tags_data["tags"].append({"name": tag_name, "color": color})
            tags_data["version"] = "1.0"
            with open(self.TAGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(tags_data, f, ensure_ascii=False, indent=2)
            return True
        return False

    def get_categories_map(self) -> Dict[str, Dict]:
        """获取分类映射字典，用于快速查找"""
        return {cat["id"]: cat for cat in self.categories}

        # 缓存当前认证用户名
        self._auth_username = None
    def get_authenticated_user(self) -> Optional[str]:
        """获取当前 Token 对应的用户名"""
        if self._auth_username:
            return self._auth_username

        if not self.github_token:
            return None

        try:
            url = f"{self.API_BASE}/user"
            response = requests.get(url, headers=self.headers)

            if response.status_code == 200:
                user_data = response.json()
                self._auth_username = user_data.get("login")
                return self._auth_username
            elif response.status_code == 401:
                print("Token 无效或已过期")
        except Exception as e:
            print(f"获取认证用户失败: {e}")

        return None

    def get_starred_repos(self, username: str, limit: int = 9999, include_starred_at: bool = True) -> List[Dict]:
        """获取用户 Star 的所有仓库

        Args:
            username: GitHub 用户名
            limit: 最大获取数量，默认 9999 表示获取全部
            include_starred_at: 是否获取 starred_at 时间（需要 Token 且只能获取自己的）
        """
        repos = []
        page = 1
        per_page = 100  # GitHub API 每页最大 100
        categories_map = self.get_categories_map()

        # 检查是否可以获取 starred_at（需要认证用户自己）
        auth_user = self.get_authenticated_user()
        can_get_starred_at = (
            include_starred_at
            and self.github_token
            and auth_user
            and auth_user.lower() == username.lower()
        )

        if can_get_starred_at:
            # 使用特殊 API 获取带 starred_at 的数据（只能获取自己的）
            starred_headers = self.headers.copy()
            starred_headers["Accept"] = "application/vnd.github.star+json"
            print(f"✓ 使用认证 API 获取 starred_at 时间戳")
        else:
            starred_headers = self.headers

        while True:
            # 使用 /user/starred 获取自己的（带 starred_at），否则用 /users/{username}/starred
            if can_get_starred_at:
                url = f"{self.API_BASE}/user/starred?page={page}&per_page={per_page}"
            else:
                url = f"{self.API_BASE}/users/{username}/starred?page={page}&per_page={per_page}"

            response = requests.get(url, headers=starred_headers)

            if response.status_code != 200:
                print(f"警告: 获取 Star 列表失败 (状态码: {response.status_code})")
                break

            data = response.json()
            if not data:
                break

            # 处理带 starred_at 的响应格式
            for item in data:
                if can_get_starred_at and "repo" in item:
                    # 格式: {"starred_at": "...", "repo": {...}}
                    repo = item["repo"]
                    repo["starred_at"] = item.get("starred_at")
                else:
                    # 标准格式
                    repo = item
                repos.append(repo)

            page += 1

            # 获取数量已足够
            if len(repos) >= limit:
                repos = repos[:limit]
                break

        # 为每个仓库匹配分类
        for repo in repos:
            category = self._match_category(repo, categories_map)
            if category:
                repo['category'] = category
            repo['matched_keywords'] = category.get('keywords', []) if category else []

        return repos

    def _match_category(self, repo: Dict, categories_map: Dict[str, Dict]) -> Optional[Dict]:
        """根据仓库信息匹配合适分类"""
        # 收集仓库的所有可匹配信息
        language = (repo.get('language') or '').lower()
        description = (repo.get('description') or '').lower()
        topics = [t.lower() for t in repo.get('topics', [])]
        name = repo.get('name', '').lower()
        full_name = repo.get('full_name', '').lower()

        # 检查每个分类的匹配度
        best_match = None
        best_score = 0

        for cat_id, cat in categories_map.items():
            score = 0
            keywords = cat.get('keywords', [])

            # 检查关键词匹配
            repo_keywords = f"{language} {description} {' '.join(topics)} {name} {full_name}"
            for kw in keywords:
                if kw.lower() in repo_keywords:
                    score += 3
                    break  # 关键词匹配得高分，不再检查其他

            # 检查语言匹配
            if language and any(kw.lower() in language for kw in keywords):
                score += 2

            # 最低要求至少有一个关键词匹配
            if score > 0 and score > best_score:
                best_match = cat
                best_score = score

        return best_match

    def get_latest_release(self, repo_full_name: str) -> Optional[Dict]:
        """获取项目的最新 Release"""
        url = f"{self.API_BASE}/repos/{repo_full_name}/releases/latest"
        response = requests.get(url, headers=self.headers)

        if response.status_code == 200:
            return response.json()
        return None

    def get_recent_commits(self, repo_full_name: str, days: int = 7) -> List[Dict]:
        """获取最近的 Commit"""
        since = (datetime.utcnow() - timedelta(days=days)).isoformat() + "Z"
        url = f"{self.API_BASE}/repos/{repo_full_name}/commits?since={since}"
        response = requests.get(url, headers=self.headers)

        if response.status_code == 200:
            return response.json()
        return []

    def get_repo_health(self, repo_full_name: str) -> Dict:
        """获取项目健康度指标"""
        url = f"{self.API_BASE}/repos/{repo_full_name}"
        response = requests.get(url, headers=self.headers)

        if response.status_code == 200:
            data = response.json()
            return {
                "stars": data.get("stargazers_count", 0),
                "forks": data.get("forks_count", 0),
                "open_issues": data.get("open_issues_count", 0),
                "updated_at": data.get("updated_at"),
                "pushed_at": data.get("pushed_at"),
                "language": data.get("language"),
                "has_wiki": data.get("has_wiki"),
                "has_pages": data.get("has_pages"),
            }
        return {}

    def get_readme(self, repo_full_name: str) -> str:
        """获取 README 内容"""
        url = f"{self.API_BASE}/repos/{repo_full_name}/readme"
        response = requests.get(url, headers=self.headers)

        if response.status_code == 200:
            content_url = response.json().get("download_url")
            if content_url:
                readme_res = requests.get(content_url)
                # 限制长度防止过长
                return readme_res.text[:6000]

    def add_star(self, repo_full_name: str) -> tuple[bool, str]:
        """为仓库添加 Star（需要 repo_deployment 权限）

        Args:
            repo_full_name: 仓库名称 (如 "owner/repo")

        Returns:
            (是否成功, 消息)
        """
        if not self.github_token:
            return False, "需要 GitHub Token"

        url = f"{self.API_BASE}/user/starred/{repo_full_name}"
        response = requests.put(url, headers=self.headers)

        if response.status_code == 204:
            return True, f"✓ 已 Star: {repo_full_name}"
        elif response.status_code == 404:
            return False, f"✗ 仓库不存在"
        else:
            return False, f"✗ 操作失败 ({response.status_code})"

    def summarize_with_ai(self, repo_info: Dict, readme: str = "", use_ai: bool = True) -> str:
        """使用 AI 总结项目

        Args:
            use_ai: 是否使用 AI（默认 True），如果为 False 则强制使用基础摘要
        """
        self._ensure_ai_client(use_ai=use_ai)
        if not self._client:
            return self._basic_summary(repo_info)

        prompt = f"""请简要分析以下 GitHub 项目：

项目名称: {repo_info['name']}
完整名称: {repo_info['full_name']}
描述: {repo_info.get('description', '无描述')}
主要语言: {repo_info.get('language', '未知')}
Stars: {repo_info.get('stargazers_count', 0)}

README 内容（前6000字）:
{readme[:2000]}

请用中文输出以下格式（简洁）：
**核心功能**: 一句话描述
**技术栈**: 主要技术/语言
**适用场景**: 什么情况下使用
"""
        try:
            response = self._client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"AI 摘要失败: {e}")
            return self._basic_summary(repo_info)

    def _ensure_ai_client(self, use_ai: bool = True):
        """确保 AI 客户端只在需要时才初始化

        Args:
            use_ai: 是否使用 AI（默认 True），如果为 False 则强制不使用 AI
        """
        if not HAS_OPENAI or self._client is not None:
            return self._use_ai == use_ai

        # 需要 AI 但客户端未初始化
        if use_ai and self._client is None:
            try:
                self._client = OpenAI()
                self._use_ai = True
            except Exception as e:
                print(f"⚠️ AI 客户端初始化失败: {e}")
                print("💡 将使用基础摘要替代")
                self._client = None
                self._use_ai = False

        # 不需要 AI 但客户端已初始化
        if not use_ai and self._client is not None:
            self._client = None
            self._use_ai = False

        return self._use_ai

    def _basic_summary(self, repo_info: Dict) -> str:
        """基础摘要（无 AI 时）"""
        return f"""**核心功能**: {repo_info.get('description', '无描述')}
**技术栈**: {repo_info.get('language', '未知')}
**Stars**: {repo_info.get('stargazers_count', 0)}"""

    def save_latest(self, repos: List[Dict]) -> Path:
        """保存最新数据（包含完整多维度信息，便于 AI 分析）"""
        latest_file = self.CACHE_DIR / "original_latest.json"
        fetch_time = datetime.now().isoformat()

        data = {
            "timestamp": fetch_time,
            "total_count": len(repos),
            "repos": [
                {
                    # 基本信息
                    "full_name": r["full_name"],
                    "name": r.get("name"),
                    "owner": r.get("owner", {}).get("login") if isinstance(r.get("owner"), dict) else None,
                    "html_url": r.get("html_url"),
                    "description": r.get("description"),
                    "homepage": r.get("homepage"),

                    # 时间维度（关键分析维度）
                    "starred_at": r.get("starred_at"),  # 用户何时 star 的（需要特殊 API）
                    "created_at": r.get("created_at"),   # 仓库创建时间
                    "updated_at": r.get("updated_at"),   # 仓库最后更新时间
                    "pushed_at": r.get("pushed_at"),     # 最后推送时间
                    "local_fetched_at": fetch_time,      # 本地抓取时间

                    # 统计数据（活跃度指标）
                    "stargazers_count": r.get("stargazers_count", 0),
                    "forks_count": r.get("forks_count", 0),
                    "watchers_count": r.get("watchers_count", 0),
                    "open_issues_count": r.get("open_issues_count", 0),

                    # 分类信息（技术栈/主题识别）
                    "language": r.get("language"),
                    "topics": r.get("topics", []),
                    "license": r.get("license", {}).get("spdx_id") if isinstance(r.get("license"), dict) else None,
                    "visibility": r.get("visibility"),

                    # 项目特征（健康度判断）
                    "is_fork": r.get("fork", False),
                    "is_archived": r.get("archived", False),
                    "is_template": r.get("is_template", False),
                    "has_wiki": r.get("has_wiki", False),
                    "has_pages": r.get("has_pages", False),
                    "has_discussions": r.get("has_discussions", False),

                    # 其他
                    "default_branch": r.get("default_branch"),
                    "size": r.get("size", 0),  # KB
                }
                for r in repos
            ],
        }

        with open(latest_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return latest_file

    def load_latest(self) -> Optional[Dict]:
        """加载最新数据"""
        latest_file = self.CACHE_DIR / "original_latest.json"

        if not latest_file.exists():
            return None

        try:
            return json.loads(latest_file.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"读取数据失败: {e}")
            return None

    def check_updates(self, username: str) -> Dict:
        """检查更新"""
        current_repos = self.get_starred_repos(username)
        latest = self.load_latest()

        if not latest:
            return {"status": "no_data", "message": "未找到历史数据，请先运行 --init"}

        old_repo_map = {r["full_name"]: r for r in latest["repos"]}
        current_map = {r["full_name"]: r for r in current_repos}

        updates = {
            "new_repos": [],
            "updated_repos": [],
            "releases": [],
            "active_repos": [],
        }

        for full_name, repo in current_map.items():
            if full_name not in old_repo_map:
                updates["new_repos"].append(repo)
            else:
                old = old_repo_map[full_name]
                if repo.get("updated_at") != old.get("updated_at"):
                    updates["updated_repos"].append(repo)

        return updates

    def get_commits_between_releases(self, repo_full_name: str, limit: int = 10) -> List[Dict]:
        """获取两个版本之间的 commits"""
        url = f"{self.API_BASE}/repos/{repo_full_name}/commits?per_page={limit}"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return response.json()
        return []

    def export_config(self, username: str, include_repos: bool = False) -> Dict:
        """导出当前配置（包含用户价值和自定义规则）"""
        config = {
            "username": username,
            "value_keywords": ["claude", "ai", "llm", "agent", "python"],
            "ignore_repos": [],
            "min_stars": 100,
        }

        if include_repos:
            repos = self.get_starred_repos(username, limit=200)
            config["tracked_repos"] = [r["full_name"] for r in repos]

        return config

    def import_config(self, config_data: Dict) -> bool:
        """导入配置"""
        required_keys = ["username"]
        for key in required_keys:
            if key not in config_data:
                return False
        return True

    def get_version_diff(self, repo_full_name: str, old_version: str, new_version: str) -> Dict:
        """获取版本之间的差异信息"""
        commits = self.get_commits_between_releases(repo_full_name, limit=20)

        return {
            "old_version": old_version,
            "new_version": new_version,
            "commits_count": len(commits),
            "commits": commits[:5],  # 只返回前5条
            "compare_url": f"https://github.com/{repo_full_name}/compare/{old_version}...{new_version}",
        }

    def generate_report(self, username: str, days: int = 7) -> str:
        """生成更新报告"""
        repos = self.get_starred_repos(username)
        updates = self.check_updates(username)
        snapshot = self.load_latest(username)

        report_lines = [
            f"# GitHub Star 更新报告",
            f"**用户**: {username}",
            f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"**追踪范围**: 最近 {len(repos)} 个 Star",
            "",
        ]

        # 新增项目
        if updates.get("new_repos"):
            report_lines.append("## 新增 Star")
            for repo in updates["new_repos"][:10]:
                report_lines.append(f"- [{repo['full_name']}]({repo['html_url']}) - {repo.get('description', '')[:60]}")
            report_lines.append("")

        # 检查有 Release 的项目
        report_lines.append("## 版本更新")
        release_count = 0
        for repo in repos[:30]:
            release = self.get_latest_release(repo["full_name"])
            if release:
                published = release.get("published_at", "")[:10]
                # 检查是否是最近发布的
                if snapshot and published > snapshot["timestamp"][:10]:
                    release_count += 1
                    report_lines.append(
                        f"### [{repo['full_name']}]({repo['html_url']}) - {release.get('tag_name')}\n"
                        f"- **发布时间**: {published}\n"
                        f"- **名称**: {release.get('name') or release.get('tag_name')}\n"
                        f"- **链接**: {release.get('html_url')}\n"
                    )

        if release_count == 0:
            report_lines.append("*本周没有新版本发布*\n")

        # 活跃项目
        report_lines.append("## 活跃项目（本周有更新）")
        active_count = 0
        for repo in repos[:30]:
            commits = self.get_recent_commits(repo["full_name"], days=days)
            if len(commits) >= 3:
                active_count += 1
                health = self.get_repo_health(repo["full_name"])
                language = health.get("language", "未知")
                report_lines.append(
                    f"### [{repo['full_name']}]({repo['html_url']})\n"
                    f"- **语言**: {language}\n"
                    f"- **本周 Commits**: {len(commits)} 次\n"
                    f"- **健康度**: {'🟢 活跃' if len(commits) > 10 else '🟡 一般'}\n"
                )

        if active_count == 0:
            report_lines.append("*本周没有显著活跃的项目*\n")

        return "\n".join(report_lines)

    # ==================== Star 管理功能 ====================

    def star_repo(self, repo_full_name: str) -> tuple[bool, str]:
        """为仓库添加 Star

        Args:
            repo_full_name: 仓库全名 (如 "owner/repo")

        Returns:
            (是否成功, 消息)
        """
        if not self.github_token:
            return False, "需要 GitHub Token 才能执行此操作"

        url = f"{self.API_BASE}/user/starred/{repo_full_name}"
        response = requests.put(url, headers=self.headers)

        if response.status_code == 204:
            return True, f"✓ 已 Star: {repo_full_name}"
        elif response.status_code == 404:
            return False, f"✗ 仓库不存在: {repo_full_name}"
        elif response.status_code == 422:
            return False, f"✗ 已经在 Star 列表中: {repo_full_name}"
        else:
            return False, f"✗ 操作失败 ({response.status_code}): {response.text}"

    def unstar_repo(self, repo_full_name: str) -> tuple[bool, str]:
        """取消仓库的 Star

        Args:
            repo_full_name: 仓库全名 (如 "owner/repo")

        Returns:
            (是否成功, 消息)
        """
        if not self.github_token:
            return False, "需要 GitHub Token 才能执行此操作"

        url = f"{self.API_BASE}/user/starred/{repo_full_name}"
        response = requests.delete(url, headers=self.headers)

        if response.status_code == 204:
            return True, f"✓ 已取消 Star: {repo_full_name}"
        elif response.status_code == 404:
            return False, f"✗ 不在 Star 列表中: {repo_full_name}"
        else:
            return False, f"✗ 操作失败 ({response.status_code}): {response.text}"

    def is_starred(self, repo_full_name: str) -> bool:
        """检查仓库是否已 Star

        Args:
            repo_full_name: 仓库全名

        Returns:
            是否已 Star
        """
        if not self.github_token:
            return False

        url = f"{self.API_BASE}/user/starred/{repo_full_name}"
        response = requests.get(url, headers=self.headers)
        return response.status_code == 204

    def batch_unstar(self, repo_list: List[str], dry_run: bool = True) -> tuple[int, int, List[str]]:
        """批量取消 Star

        Args:
            repo_list: 仓库列表
            dry_run: 试运行模式（不实际执行）

        Returns:
            (成功数, 失败数, 失败列表)
        """
        success = 0
        failed = []
        failed_repos = []

        for repo in repo_list:
            print(f"[{'DRY-RUN' if dry_run else '执行'}] 取消 Star: {repo}", end=" ")

            if dry_run:
                print("→ 跳过")
                continue

            success_flag, msg = self.unstar_repo(repo)
            print(f"→ {msg}")

            if success_flag:
                success += 1
            else:
                failed += 1
                failed_repos.append(repo)

        return success, failed, failed_repos

    def batch_star(self, repo_list: List[str], dry_run: bool = True) -> tuple[int, int, List[str]]:
        """批量添加 Star

        Args:
            repo_list: 仓库列表
            dry_run: 试运行模式

        Returns:
            (成功数, 失败数, 失败列表)
        """
        success = 0
        failed = []
        failed_repos = []

        for repo in repo_list:
            print(f"[{'DRY-RUN' if dry_run else '执行'}] 添加 Star: {repo}", end=" ")

            if dry_run:
                print("→ 跳过")
                continue

            success_flag, msg = self.star_repo(repo)
            print(f"→ {msg}")

            if success_flag:
                success += 1
            else:
                failed += 1
                failed_repos.append(repo)

        return success, failed, failed_repos

    def cleanup_stale_repos(self, username: str, days_threshold: int = 90, dry_run: bool = True) -> tuple[int, List[str]]:
        """清理长期未更新的仓库（建议取消 Star）

        Args:
            username: GitHub 用户名
            days_threshold: 多少天未更新视为"陈旧"
            dry_run: 试运行模式

        Returns:
            (建议取消数, 仓库列表)
        """
        repos = self.get_starred_repos(username, limit=200)
        stale_repos = []

        print(f"\n检查 {len(repos)} 个 Star 项目（阈值: {days_threshold} 天）...")

        for repo in repos:
            updated = datetime.fromisoformat(repo.get("updated_at", "").replace("Z", "+00:00"))
            days_since = (datetime.now() - updated).days

            if days_since > days_threshold:
                stale_repos.append({
                    "full_name": repo["full_name"],
                    "days_since_update": days_since,
                    "last_commit": updated.strftime("%Y-%m-%d"),
                    "stars": repo.get("stargazers_count", 0),
                })

        # 排序：按未更新天数
        stale_repos.sort(key=lambda x: x["days_since_update"], reverse=True)

        print(f"\n找到 {len(stale_repos)} 个长期未更新的项目：")
        for repo in stale_repos[:20]:
            print(f"  - {repo['full_name']}: {repo['days_since_update']} 天未更新")

        if len(stale_repos) > 20:
            print(f"  ... 还有 {len(stale_repos) - 20} 个")

        return len(stale_repos), [r["full_name"] for r in stale_repos]

