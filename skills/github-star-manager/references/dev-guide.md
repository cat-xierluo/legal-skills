# 开发指南

本文档面向 github-star-manager 的开发者，提供架构说明和开发指导。

## 代码架构

### 文件职责

| 文件 | 职责 |
|------|------|
| `scripts/main.py` | CLI 入口，命令解析和分发 |
| `scripts/star_tracker.py` | 核心逻辑：API 调用、数据处理 |
| `assets/dashboard.example.html` | Dashboard 模板 |

### 数据流向

```
用户输入 (CLI)
    ↓
main.py (命令解析)
    ↓
star_tracker.py (API 调用)
    ↓
获取数据 (repos, releases, commits)
    ↓
生成 JSON 数据
    ↓
dashboard.html (浏览器渲染)
```

## 核心类设计

### StarTracker 类

```python
class StarTracker:
    def __init__(self, github_token):        # 初始化请求头
    def get_starred_repos(self, username):      # 获取 Star 列表
    def get_latest_release(self, repo_full_name):   # 获取最新 Release
    def get_recent_commits(self, repo_full_name, days): # 获取最近 Commits
    def get_repo_health(self, repo_full_name):       # 获取仓库健康度
    def get_readme(self, repo_full_name):           # 获取 README
    def load_snapshot(self, username):             # 加载本地快照
    def save_snapshot(self, username, repos):       # 保存快照
    def check_updates(self, username):             # 检查更新
    def get_commits_between_releases(self, ...):  # 获取版本间 Commits (新增)
    def export_config(self, ...):                # 导出配置 (新增)
    def import_config(self, ...):                # 导入配置 (新增)
    def get_version_diff(self, ...):              # 获取版本差异 (新增)
```

## 扩展指南

### 添加新功能

1. 在 `StarTracker` 类中添加新方法
2. 更新 `scripts/main.py` 中的命令处理
3. 如需新依赖，添加到 `assets/requirements.txt`
4. 更新 `SKILL.md` 和 `CHANGELOG.md`

### 代码规范

1. **错误处理**：所有 API 调用必须有 try-except
2. **日志输出**：使用 print() 显示进度，不是 logging
3. **类型提示**：函数签名使用类型注解
4. **常量管理**：API URL 等定义为类常量

## 测试

### 手动测试
```bash
# 进入脚本目录
cd skills/github-star-manager

# 测试获取 Star（不使用 Token）
python3 -c "from star_tracker import StarTracker; t = StarTracker(); print(t.get_starred_repos('yourname'))"

# 测试导出配置
python3 -c "from star_tracker import StarTracker; t = StarTracker(); print(t.export_config('testuser'))"
```

### 集成测试

确保添加新功能后：
1. 不破坏现有功能
2. 兼容现有配置文件格式
3. Dashboard 正确显示新数据
