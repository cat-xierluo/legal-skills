"""
GitHub Star 追踪器 - 核心分析模块
支持更新检测、版本追踪、活跃度分析、分类和标签管理
"""

import os
import json
import time

try:
    import yaml
except ImportError:
    yaml = None  # 分类 YAML 加载时给出安装提示，见 _load_categories

try:
    import requests
except ImportError:
    print("❌ 缺少依赖: requests")
    print("   请运行: pip install requests")
    print("   或运行: pip install -r assets/requirements.txt")
    raise SystemExit(1)

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    OpenAI = None
    HAS_OPENAI = False  # AI 摘要可选：缺失时自动降级为基础摘要（修复 F03 NameError）

from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Set
from pathlib import Path


class SnapshotConflictError(RuntimeError):
    """R6/J1a+J1b：基线被外部写者推进（CAS 失败）或跨进程锁不可用时，
    save_latest fail-closed 拒绝写入的显式信号。调用方可重读最新基线后重试。"""


def _atomic_replace(path: Path, text: str) -> None:
    """tmp + os.replace 原子替换（读者永不见半截文件）。"""
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


class StarTracker:
    """GitHub Star 更新追踪器"""

    API_BASE = "https://api.github.com"
    # 使用项目目录内的 output/ 目录（自包含项目原则）
    CACHE_DIR = Path(__file__).parent.parent / "output"
    CONFIG_DIR = CACHE_DIR  # 配置文件目录

    # 网络请求重试配置（代理长跑抖动容错）
    RETRY_MAX_ATTEMPTS = 8
    RETRY_INITIAL_DELAY = 2      # 秒，指数退避起点
    RETRY_MAX_DELAY = 60         # 秒，退避封顶
    RETRY_STATUS_CODES = {429, 500, 502, 503, 504}  # 触发重试的状态码

    # 配置文件路径
    CATEGORIES_FILE = CONFIG_DIR / "categories.yaml"
    TAGS_FILE = CONFIG_DIR / "tags.json"
    SETTINGS_FILE = CONFIG_DIR / "user_settings.json"

    def __init__(self, github_token: Optional[str] = None):
        self.github_token = github_token or os.getenv("GITHUB_PAT")
        self.user = None
        self._auth_username = None
        # 最近一次 get_starred_repos 的抓取完整性元数据（审计 F01）
        self.last_fetch_meta: Optional[Dict] = None
        # AI 客户端惰性初始化状态（F03：此前未初始化即被 _ensure_ai_client 引用）
        self._client = None
        self._use_ai = False
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

    def _request_with_retry(self, method: str, url: str, timeout: int = 30,
                            **kwargs) -> Optional[requests.Response]:
        """带指数退避重试的请求封装

        代理长跑场景（如全量导出数百个仓库）下，HTTP 503 隧道错误与
        RemoteDisconnected 闪断是常态而非异常。裸 requests 调用一次即崩，
        673 仓的导出窗口内必折。本方法统一容错：

        - 网络异常（ConnectionError/Timeout/RemoteDisconnected 等均归入
          requests.RequestException）：指数退避后重试
        - 429/5xx 状态码：同样退避重试（429 尊重 Retry-After 头）
        - 其他状态码（401/404/422 等）：语义明确，原样返回不重试

        Returns:
            最终响应。网络异常重试耗尽时返回 None（无响应可给）；
            状态码类重试耗尽时返回最后一个响应（如 503），调用方按既有
            「is None or status_code != 200」分支处理，可检查真实状态码
        """
        delay = self.RETRY_INITIAL_DELAY
        for attempt in range(1, self.RETRY_MAX_ATTEMPTS + 1):
            try:
                response = requests.request(method, url, timeout=timeout, **kwargs)
                if response.status_code in self.RETRY_STATUS_CODES:
                    retry_after = response.headers.get("Retry-After")
                    wait = int(retry_after) if (retry_after and retry_after.isdigit()) else delay
                    if attempt < self.RETRY_MAX_ATTEMPTS:
                        print(f"  [retry] HTTP {response.status_code}，{wait}s 后第 {attempt}/{self.RETRY_MAX_ATTEMPTS} 次重试: {url}")
                        time.sleep(wait)
                        delay = min(delay * 2, self.RETRY_MAX_DELAY)
                        continue
                return response
            except requests.RequestException as e:
                if attempt >= self.RETRY_MAX_ATTEMPTS:
                    print(f"  [retry] 重试耗尽（{self.RETRY_MAX_ATTEMPTS} 次）: {url} · {e}")
                    return None
                print(f"  [retry] 网络异常，{delay}s 后第 {attempt}/{self.RETRY_MAX_ATTEMPTS} 次重试: {type(e).__name__}")
                time.sleep(delay)
                delay = min(delay * 2, self.RETRY_MAX_DELAY)
        return None

    def _load_categories(self) -> List[Dict]:
        """加载分类配置"""
        if self.CATEGORIES_FILE.exists():
            if yaml is None:
                print("⚠️ 检测到分类配置但缺少依赖: pyyaml")
                print("   请运行: pip install pyyaml（或 pip install -r assets/requirements.txt）")
                print("   本次将使用内置默认分类")
            else:
                try:
                    with open(self.CATEGORIES_FILE, 'r', encoding='utf-8') as f:
                        loaded = yaml.safe_load(f)
                        # 兼容两种格式：裸列表 或 {categories: [...]}（generate_categories.py 生成后者）
                        if isinstance(loaded, dict) and 'categories' in loaded:
                            loaded = loaded['categories']
                        if isinstance(loaded, list) and loaded:
                            return loaded
                        # 空文件/空列表：回落默认
                except Exception as e:
                    # 不静默：环境问题（如旧版 pyyaml 与新版 Python 不兼容）必须可见
                    print(f"⚠️ 分类配置加载失败（{type(e).__name__}: {e}），本次使用内置默认分类")
                    print(f"   配置文件: {self.CATEGORIES_FILE}")
                    print("   若为 pyyaml 版本过旧（<6.0）请运行: pip install -U pyyaml")
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

    def get_authenticated_user(self) -> Optional[str]:
        """获取当前 Token 对应的用户名"""
        if self._auth_username:
            return self._auth_username

        if not self.github_token:
            return None

        try:
            url = f"{self.API_BASE}/user"
            response = self._request_with_retry("GET", url, headers=self.headers)
            if response is None:
                return None

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

        分页中途失败不再静默返回子集（审计 F01）：完整抓取状态记录在
        self.last_fetch_meta，调用方在提交快照前必须检查 complete 字段，
        部分数据只能作临时对比，不得覆盖基线。

        Args:
            username: GitHub 用户名
            limit: 最大获取数量，默认 9999 表示获取全部
            include_starred_at: 是否获取 starred_at 时间（需要 Token 且只能获取自己的）
        """
        repos = []
        page = 1
        per_page = 100  # GitHub API 每页最大 100
        categories_map = self.get_categories_map()

        fetch_meta = {
            "account_id": username,
            "complete": True,
            "failed_pages": [],
            "limit_requested": limit,
            "limit_truncated": False,
            "starred_at_available": False,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

        # 检查是否可以获取 starred_at（需要认证用户自己）
        auth_user = self.get_authenticated_user()
        can_get_starred_at = (
            include_starred_at
            and self.github_token
            and auth_user
            and auth_user.lower() == username.lower()
        )
        fetch_meta["starred_at_available"] = bool(can_get_starred_at)

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

            response = self._request_with_retry("GET", url, headers=starred_headers)

            if response is None or response.status_code != 200:
                status_desc = str(response.status_code) if response else "网络异常重试耗尽"
                print(f"警告: 获取 Star 列表失败 (状态码: {status_desc})")
                # F01: 标记抓取不完整，由调用方决定是否允许提交快照
                fetch_meta["complete"] = False
                fetch_meta["failed_pages"].append({"page": page, "status": status_desc})
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

            # 获取数量已足够（R5/J5：limit 截断 ≠ 完整快照——上游 F01 反例：
            # --check --limit 1 标 limit_truncated=true 却仍称 complete，把未抓到的
            # 旧条目误判为「取消收藏」。截断时 complete 必须为 False。）
            if len(repos) >= limit:
                repos = repos[:limit]
                fetch_meta["limit_truncated"] = True
                fetch_meta["complete"] = False   # 截断即非完整快照
                break

        # 为每个仓库匹配分类
        for repo in repos:
            category = self._match_category(repo, categories_map)
            if category:
                repo['category'] = category
            repo['matched_keywords'] = category.get('keywords', []) if category else []

        self.last_fetch_meta = fetch_meta
        return repos

    def _match_category(self, repo: Dict, categories_map: Dict[str, Dict]) -> Optional[Dict]:
        """根据仓库信息匹配合适分类

        0.8.0 起与 quick_export.py 共用统一评分规则（common.match_categories），
        收敛审计「分类/导出分叉」：在线单分类 = 多标签结果的首个（min_score=1）。
        """
        from common import match_categories
        best = match_categories(repo, list(categories_map.values()), min_score=1)
        return best[0] if best else None

    def get_latest_release(self, repo_full_name: str) -> Optional[Dict]:
        """获取项目的最新 Release"""
        url = f"{self.API_BASE}/repos/{repo_full_name}/releases/latest"
        response = self._request_with_retry("GET", url, headers=self.headers)

        if response is not None and response.status_code == 200:
            return response.json()
        return None

    def get_recent_commits(self, repo_full_name: str, days: int = 7) -> List[Dict]:
        """获取最近的 Commit"""
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        url = f"{self.API_BASE}/repos/{repo_full_name}/commits?since={since}"
        response = self._request_with_retry("GET", url, headers=self.headers)

        if response is not None and response.status_code == 200:
            return response.json()
        return []

    def get_repo_health(self, repo_full_name: str) -> Dict:
        """获取项目健康度指标"""
        url = f"{self.API_BASE}/repos/{repo_full_name}"
        response = self._request_with_retry("GET", url, headers=self.headers)

        if response is not None and response.status_code == 200:
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

    def refresh_repo_metadata(self, repo_full_name: str) -> Optional[Dict]:
        """刷新单个仓库的最新元数据（description、language 等）

        通过 GitHub API 获取最新的仓库信息，用于：
        1. description 为 null 时重新抓取
        2. 项目改名后刷新存量数据
        3. star 变化时同步更新元数据

        Returns:
            包含最新元数据的字典，失败时返回 None
        """
        url = f"{self.API_BASE}/repos/{repo_full_name}"
        response = self._request_with_retry("GET", url, headers=self.headers)

        if response is not None and response.status_code == 200:
            return response.json()
        elif response is not None and response.status_code == 404:
            print(f"  ⚠ 仓库不存在或已删除: {repo_full_name}")
        elif response is None:
            print(f"  ⚠ 获取元数据失败 (网络异常重试耗尽): {repo_full_name}")
        else:
            print(f"  ⚠ 获取元数据失败 ({response.status_code}): {repo_full_name}")
        return None

    def log_null_descriptions(self, repos: List[Dict], source: str = "unknown") -> List[str]:
        """记录 description 为 null 的项目，用于数据质量排查

        Args:
            repos: 仓库列表
            source: 数据来源标识（如 "latest", "incremental"）

        Returns:
            description 为 null 的仓库 full_name 列表
        """
        null_desc_repos = []
        for repo in repos:
            full_name = repo.get("full_name", "unknown")
            desc = repo.get("description")
            if desc is None:
                null_desc_repos.append(full_name)

        if null_desc_repos:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n📊 [数据质量] 来源={source}, description 为 null 的项目 ({len(null_desc_repos)} 个):")
            for fn in null_desc_repos[:20]:
                print(f"  - {fn}")
            if len(null_desc_repos) > 20:
                print(f"  ... 还有 {len(null_desc_repos) - 20} 个")

            # 写入数据质量日志文件
            log_file = self.CACHE_DIR / "data_quality.log"
            try:
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(f"\n[{timestamp}] source={source}\n")
                    for fn in null_desc_repos:
                        f.write(f"  null_description: {fn}\n")
            except Exception as e:
                print(f"  ⚠ 写入数据质量日志失败: {e}")

        return null_desc_repos

    def retry_null_descriptions(self, repos: List[Dict]) -> List[Dict]:
        """对 description 为 null 的项目重新抓取元数据

        逐个调用 GitHub API 获取最新仓库信息，用返回的 description 替换 null 值。
        同时刷新 language、topics 等可能变化的元数据字段。

        Args:
            repos: 当前仓库列表

        Returns:
            更新后的仓库列表
        """
        null_repos = [r for r in repos if r.get("description") is None]
        if not null_repos:
            return repos

        print(f"\n🔄 发现 {len(null_repos)} 个项目 description 为 null，正在重新抓取元数据...")
        refreshed_count = 0
        still_null = []

        repo_map = {r["full_name"]: i for i, r in enumerate(repos)}

        for repo in null_repos:
            full_name = repo.get("full_name")
            if not full_name:
                continue

            fresh_data = self.refresh_repo_metadata(full_name)
            if fresh_data:
                idx = repo_map[full_name]
                # 更新 description
                repos[idx]["description"] = fresh_data.get("description")
                # 同时刷新其他可能变化的元数据
                repos[idx]["language"] = fresh_data.get("language", repos[idx].get("language"))
                repos[idx]["topics"] = fresh_data.get("topics", repos[idx].get("topics", []))
                repos[idx]["homepage"] = fresh_data.get("homepage", repos[idx].get("homepage"))
                repos[idx]["stargazers_count"] = fresh_data.get("stargazers_count", repos[idx].get("stargazers_count", 0))
                repos[idx]["forks_count"] = fresh_data.get("forks_count", repos[idx].get("forks_count", 0))
                repos[idx]["updated_at"] = fresh_data.get("updated_at", repos[idx].get("updated_at"))
                repos[idx]["pushed_at"] = fresh_data.get("pushed_at", repos[idx].get("pushed_at"))

                new_desc = fresh_data.get("description")
                if new_desc is not None:
                    refreshed_count += 1
                    print(f"  ✓ {full_name}: description 已更新 → {new_desc[:60]}")
                else:
                    still_null.append(full_name)
                    print(f"  - {full_name}: API 返回 description 仍为 null")
            else:
                still_null.append(full_name)
                print(f"  ✗ {full_name}: 元数据获取失败")

        print(f"\n📊 description 重试结果: 成功 {refreshed_count}/{len(null_repos)}")
        if still_null:
            print(f"  仍为 null 的项目: {', '.join(still_null[:10])}")

        return repos

    def get_readme(self, repo_full_name: str) -> str:
        """获取 README 内容"""
        url = f"{self.API_BASE}/repos/{repo_full_name}/readme"
        response = self._request_with_retry("GET", url, headers=self.headers)

        if response is not None and response.status_code == 200:
            content_url = response.json().get("download_url")
            if content_url:
                readme_res = self._request_with_retry("GET", content_url, timeout=60)
                if readme_res is not None and readme_res.status_code == 200:
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
        response = self._request_with_retry("PUT", url, headers=self.headers)

        if response is not None and response.status_code == 204:
            return True, f"✓ 已 Star: {repo_full_name}"
        elif response is not None and response.status_code == 404:
            return False, f"✗ 仓库不存在"
        elif response is None:
            return False, f"✗ 网络异常重试耗尽"
        else:
            return False, f"✗ 操作失败 ({response.status_code})"

    def summarize_with_ai(self, repo_info: Dict, readme: str = "", use_ai: bool = True) -> str:
        """使用 AI 总结项目

        Args:
            use_ai: 是否使用 AI（默认 True）。openai 未安装或初始化失败时自动降级为基础摘要。
        """
        if not self._ensure_ai_client(use_ai=use_ai) or not self._client:
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

    def _ensure_ai_client(self, use_ai: bool = True) -> bool:
        """确保 AI 客户端只在需要时才初始化

        Args:
            use_ai: 是否使用 AI（默认 True），如果为 False 则强制不使用 AI

        Returns:
            本次调用结束时 AI 摘要是否可用（HAS_OPENAI 为 False 时恒为 False）
        """
        if not use_ai:
            return False

        if not HAS_OPENAI:
            print("💡 未安装 openai 包，使用基础摘要替代（可选: pip install openai）")
            return False

        if self._client is not None:
            return True

        try:
            self._client = OpenAI()
            self._use_ai = True
            return True
        except Exception as e:
            print(f"⚠️ AI 客户端初始化失败: {e}")
            print("💡 将使用基础摘要替代")
            self._client = None
            self._use_ai = False
            return False

    def _basic_summary(self, repo_info: Dict) -> str:
        """基础摘要（无 AI 时）"""
        return f"""**核心功能**: {repo_info.get('description', '无描述')}
**技术栈**: {repo_info.get('language', '未知')}
**Stars**: {repo_info.get('stargazers_count', 0)}"""

    # R6/J1a：跨写者前向合并保留的插件扩展字段（技能全量快照不该丢这些）
    FORWARD_MERGE_FIELDS = ("description_zh", "tags_zh", "_lite", "reason",
                            "matched_keywords")

    # B 方案（单权威写者）协议版本：save_latest 的规范化已直通上述插件扩展字段
    # （description_zh/tags_zh/_lite 输入有则写入），star-board 插件据此把
    # original_latest.json 的全部写入路由给 save_latest 而无需锁外补写。
    # v2 完整合同（协议 2 ⇒ 以下全部成立，插件按此调用）：
    #   a) 双形态输入：owner/license 接受 dict（GitHub 原始对象）或 str（v2 快照行）；
    #      is_fork/is_archived 接受原始键 fork/archived 或 v2 键——v2 规范化行往返不降级
    #   b) normalized_rows=True：输入已是 v2 快照行（含插件扩展字段，如 category/
    #      value/avatar_url/has_new_release），未列入已知映射的键**原样直通**（raw
    #      输入路径不受影响，仍剥离未知键）
    #   c) lock_timeout：显式锁超时秒数（None → lockutil 默认）——调用方不得临时
    #      改 lockutil._DEFAULT_TIMEOUT 全局（并行调用还原竞态）
    #   d) description_zh/tags_zh/_lite：输入有值则写入；_lite 缺省/非 bool 写 None
    #      （前向合并可从现有快照回填，显式 False 保留——缺省与显式假值必须可区分）
    # 注意：协议 2 是「唯一写入口实现」，不是单一常驻写进程——多进程并发调用时
    # flock/CAS/冲突语义仍然生效。
    SNAPSHOT_WRITER_PROTOCOL = 2

    def save_latest(self, repos: List[Dict], fetch_meta: Optional[Dict] = None,
                    base_timestamp: Optional[str] = None,
                    normalized_rows: bool = False,
                    lock_timeout: Optional[float] = None) -> Path:
        """保存最新数据（包含完整多维度信息，便于 AI 分析）

        Args:
            repos: 仓库列表。默认按 GitHub 原始对象规范化；normalized_rows=True 时
                输入是 v2 快照行（含插件扩展字段），已知映射兼容双形态，未知键直通
                （协议 2 合同 b，见 SNAPSHOT_WRITER_PROTOCOL 注释）。
            fetch_meta: 抓取完整性元数据（来自 get_starred_repos 的 last_fetch_meta）。
                不传时按「完整性未知」处理，快照标记为 partial 并说明原因。
            base_timestamp: 调用方读取本次对比基线时的快照 timestamp（R6/J1a CAS）。
                提供时，锁内重读当前快照：若 timestamp 已被外部写者推进 → 抛
                SnapshotConflictError（fail-closed，调用方用最新数据重读后再写）；
                否则在锁内做扩展字段前向合并（description_zh 等插件产物不被全量快照冲掉）。
            lock_timeout: 获取写锁的最长等待秒数；None → lockutil 默认。协议 2 调用方
                必须用此参数传超时，不得临时修改 lockutil 全局默认值。
        """
        latest_file = self.CACHE_DIR / "original_latest.json"
        fetch_time = datetime.now().isoformat()

        if fetch_meta is None:
            snapshot_meta = {
                "complete": False,
                "completeness": "unknown",
                "note": "保存时未提供抓取元数据，无法证明快照完整",
            }
        else:
            snapshot_meta = dict(fetch_meta)
            snapshot_meta["completeness"] = "complete" if fetch_meta.get("complete") else "partial"

        def _normalize(r: Dict) -> Dict:
            """单行规范化（协议 2 双形态合同）。

            GitHub 原始对象与 v2 快照行都接受：owner/license 兼容 dict/str，
            fork/archived 兼容原始键/v2 键（is_fork/is_archived）。v2 行经此函数
            往返不得降级（B1：插件把读出的快照行原样写回时字段保真）。
            """
            row = {
                # 基本信息
                # id：GitHub 数字主键，改名后保持稳定（消费者应以 id 为主键、
                # full_name 为展示名，避免改名被误判为新仓库——D-00 对账发现的缺口）
                "id": r.get("id"),
                "full_name": r["full_name"],
                "name": r.get("name"),
                "owner": (r.get("owner") or {}).get("login")
                    if isinstance(r.get("owner"), dict) else r.get("owner"),
                "html_url": r.get("html_url"),
                "description": r.get("description"),
                "homepage": r.get("homepage"),

                # 时间维度（关键分析维度）
                "starred_at": r.get("starred_at"),  # 用户何时 star 的（需要特殊 API）
                "created_at": r.get("created_at"),   # 仓库创建时间
                "updated_at": r.get("updated_at"),   # 仓库最后更新时间
                "pushed_at": r.get("pushed_at"),     # 最后推送时间
                # 原始对象无此键 → fetch_time；v2 行已有 → 保留（插件写入不是重新抓取）
                "local_fetched_at": r.get("local_fetched_at", fetch_time),

                # 统计数据（活跃度指标）
                "stargazers_count": r.get("stargazers_count", 0),
                "forks_count": r.get("forks_count", 0),
                "watchers_count": r.get("watchers_count", 0),
                "open_issues_count": r.get("open_issues_count", 0),

                # 分类信息（技术栈/主题识别）
                "language": r.get("language"),
                "topics": r.get("topics", []),
                "license": (r.get("license") or {}).get("spdx_id")
                    if isinstance(r.get("license"), dict) else r.get("license"),
                "visibility": r.get("visibility"),

                # 项目特征（健康度判断）——原始键 fork/archived 与 v2 键 is_fork/
                # is_archived 双兼容
                "is_fork": bool(r.get("fork", r.get("is_fork", False))),
                "is_archived": bool(r.get("archived", r.get("is_archived", False))),
                "is_template": bool(r.get("is_template", False)),
                "has_wiki": bool(r.get("has_wiki", False)),
                "has_pages": bool(r.get("has_pages", False)),
                "has_discussions": bool(r.get("has_discussions", False)),

                # 其他
                "default_branch": r.get("default_branch"),
                "size": r.get("size", 0),  # KB

                # B 方案：插件扩展字段直通（输入有则写入；无则 None——None 可被
                # 前向合并从现有快照回填）。_lite 缺省/非 bool → None 而非 False：
                # False 是合法显式值，写死 False 会让旧 true 无法回填（B3）
                "description_zh": r.get("description_zh"),
                "tags_zh": r.get("tags_zh"),
                "_lite": r["_lite"] if isinstance(r.get("_lite"), bool) else None,
            }
            if normalized_rows:
                # 协议 2 合同 b：v2 快照行的插件扩展字段（category/value/avatar_url/
                # has_new_release 等）原样直通，不因不在已知映射而被剥掉。仅显式
                # 声明 normalized_rows 的调用方（插件 B 路径）可触发；raw 输入路径
                # 仍按白名单剥离未知键，行为不变。
                for k, v in r.items():
                    if k not in row:
                        row[k] = v
            return row

        data = {
            "schema_version": 2,
            "timestamp": fetch_time,
            "total_count": len(repos),
            "snapshot_meta": snapshot_meta,
            "repos": [_normalize(r) for r in repos],
        }

        # R6/J1a + J1b：锁内重读 + CAS + 前向合并，fail-closed。
        # 与 star-board 插件共用 output/.gsm-write.lock；读-改-写在同一锁内完成，
        # 不再"锁外读、锁内盲覆盖"（上游 J1a 反例：插件确认条目被旧读覆盖）。
        from lockutil import write_lock, LockUnavailable

        def _commit_locked():
            cur = None
            if latest_file.exists():
                try:
                    cur = json.loads(latest_file.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    cur = None
            # CAS：基线被外部写者推进则拒绝旧提交
            if base_timestamp is not None and isinstance(cur, dict):
                if cur.get("timestamp") != base_timestamp:
                    raise SnapshotConflictError(
                        f"快照基线已被外部写者推进（{base_timestamp} → "
                        f"{cur.get('timestamp')}），本次基于旧读的写入被拒绝（fail-closed），"
                        f"请用最新数据重读后再写")
            merged = dict(data)
            # 前向合并：保留 cur 中插件扩展字段（技能 repos 不含它们）
            if isinstance(cur, dict) and isinstance(cur.get("repos"), list):
                cur_extra = {r.get("full_name"): r for r in cur["repos"] if r.get("full_name")}
                for r in merged["repos"]:
                    ex = cur_extra.get(r.get("full_name"))
                    if ex:
                        for fld in self.FORWARD_MERGE_FIELDS:
                            if r.get(fld) in (None, "", []) and fld in ex:
                                r[fld] = ex[fld]
            merged["timestamp"] = datetime.now().isoformat()
            _atomic_replace(latest_file, json.dumps(merged, ensure_ascii=False, indent=2))

        try:
            with write_lock(self.CACHE_DIR, timeout=lock_timeout):
                _commit_locked()
        except LockUnavailable as e:
            # J1b fail-closed：锁不可用/超时绝不退回无锁写
            raise SnapshotConflictError(f"跨进程写锁不可用（{e}），已拒绝写入，旧数据保持不变") from e

        return latest_file

    def load_latest(self) -> Optional[Dict]:
        """加载最新数据（兼容 v1 无元数据快照）"""
        latest_file = self.CACHE_DIR / "original_latest.json"

        if not latest_file.exists():
            return None

        try:
            data = json.loads(latest_file.read_text(encoding="utf-8"))
            # v1 快照（无 snapshot_meta）标记完整性未知，避免被当成完整快照消费
            if "snapshot_meta" not in data:
                data["snapshot_meta"] = {
                    "complete": False,
                    "completeness": "unknown",
                    "note": "v1 旧快照，无抓取完整性元数据",
                }
            return data
        except Exception as e:
            print(f"读取数据失败: {e}")
            return None

    @staticmethod
    def is_snapshot_submittable(snapshot: Optional[Dict]) -> tuple[bool, str]:
        """判断快照能否作为新基线提交（审计 F01 守卫）

        Returns:
            (是否可提交, 不可提交的原因)
        """
        if not snapshot:
            return False, "快照不存在"
        meta = snapshot.get("snapshot_meta") or {}
        # R5/J5：limit 截断的快照不是完整基线（上游 F01：截断却称完整 → 误判取消）
        if meta.get("limit_truncated") is True:
            return False, ("快照为 limit 截断的子集（limit_truncated=true），"
                           "不允许作为基线覆盖旧数据")
        if meta.get("complete") is True:
            return True, ""
        completeness = meta.get("completeness", "unknown")
        return False, f"快照完整性为 {completeness}（complete={meta.get('complete')}），不允许作为基线覆盖旧数据"

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
        response = self._request_with_retry("GET", url, headers=self.headers)
        if response is not None and response.status_code == 200:
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
        """校验并持久化配置到 user_settings.json

        此前只校验不落盘（审计第 6 节：设置从未进入价值判断），
        现在校验通过即写入 user_settings.json，assess_value 等可读取。
        """
        required_keys = ["username"]
        for key in required_keys:
            if key not in config_data:
                return False
        return self.save_settings(config_data)

    def save_settings(self, settings: Dict) -> bool:
        """保存用户设置到 user_settings.json"""
        try:
            with open(self.SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
            self.settings = settings
            return True
        except Exception as e:
            print(f"⚠️ 保存设置失败: {e}")
            return False

    def get_value_config(self) -> Dict:
        """读取价值评估配置（value_keywords/min_stars），供价值判断使用"""
        return {
            "value_keywords": self.settings.get("value_keywords",
                ["claude", "ai", "llm", "agent", "python"]),
            "min_stars": self.settings.get("min_stars", 100),
            "ignore_repos": self.settings.get("ignore_repos", []),
        }

    def get_version_diff(self, repo_full_name: str, old_version: str, new_version: str) -> Dict:
        """获取两个版本（tag/分支/commit）之间的真实差异

        修复审计「版本对比名实不符」：此前只是取最近 N 条 commits 加上
        一个 compare_url，并未真正做版本间比较。现改用 GitHub compare API。

        Args:
            repo_full_name: 仓库全名 (owner/repo)
            old_version: 基准版本（tag 名如 v1.0.0，或分支名/commit SHA）
            new_version: 目标版本
        """
        url = f"{self.API_BASE}/repos/{repo_full_name}/compare/{old_version}...{new_version}"
        response = self._request_with_retry("GET", url, headers=self.headers)

        if response is None:
            return {
                "error": "网络异常重试耗尽",
                "old_version": old_version,
                "new_version": new_version,
                "compare_url": f"https://github.com/{repo_full_name}/compare/{old_version}...{new_version}",
            }
        if response.status_code == 404:
            return {
                "error": f"仓库或版本不存在（检查 tag 是否正确）: {repo_full_name} {old_version}...{new_version}",
                "old_version": old_version,
                "new_version": new_version,
                "compare_url": f"https://github.com/{repo_full_name}/compare/{old_version}...{new_version}",
            }
        if response.status_code != 200:
            return {
                "error": f"GitHub API 返回 {response.status_code}",
                "old_version": old_version,
                "new_version": new_version,
                "compare_url": f"https://github.com/{repo_full_name}/compare/{old_version}...{new_version}",
            }

        data = response.json()
        commits = data.get("commits", [])
        return {
            "old_version": old_version,
            "new_version": new_version,
            "status": data.get("status"),          # ahead/behind/identical 等
            "ahead_by": data.get("ahead_by"),
            "behind_by": data.get("behind_by"),
            "total_commits": data.get("total_commits", len(commits)),
            "commits_count": data.get("total_commits", len(commits)),  # 兼容旧字段名
            "commits": commits,
            "compare_url": f"https://github.com/{repo_full_name}/compare/{old_version}...{new_version}",
        }

    def generate_report(self, username: str, days: int = 7) -> str:
        """生成更新报告"""
        repos = self.get_starred_repos(username)
        updates = self.check_updates(username)
        snapshot = self.load_latest()  # F03: load_latest 不接受 username 参数

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
        response = self._request_with_retry("PUT", url, headers=self.headers)

        if response is not None and response.status_code == 204:
            return True, f"✓ 已 Star: {repo_full_name}"
        elif response is not None and response.status_code == 404:
            return False, f"✗ 仓库不存在: {repo_full_name}"
        elif response is not None and response.status_code == 422:
            return False, f"✗ 已经在 Star 列表中: {repo_full_name}"
        elif response is None:
            return False, f"✗ 网络异常重试耗尽"
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
        response = self._request_with_retry("DELETE", url, headers=self.headers)

        if response is not None and response.status_code == 204:
            return True, f"✓ 已取消 Star: {repo_full_name}"
        elif response is not None and response.status_code == 404:
            return False, f"✗ 不在 Star 列表中: {repo_full_name}"
        elif response is None:
            return False, f"✗ 网络异常重试耗尽"
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
        response = self._request_with_retry("GET", url, headers=self.headers)
        return response is not None and response.status_code == 204

    def batch_unstar(self, repo_list: List[str], dry_run: bool = True) -> tuple[int, int, List[str]]:
        """批量取消 Star

        Args:
            repo_list: 仓库列表
            dry_run: 试运行模式（不实际执行）

        Returns:
            (成功数, 失败数, 失败列表)
        """
        success = 0
        failed = 0
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
        failed = 0
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

        now = datetime.now(timezone.utc)  # 与 API 返回的 aware 时间统一（修复 naive/aware 相减崩溃）
        for repo in repos:
            updated = datetime.fromisoformat(repo.get("updated_at", "").replace("Z", "+00:00"))
            days_since = (now - updated).days

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

