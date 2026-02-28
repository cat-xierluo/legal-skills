# 变更日志 (CHANGELOG.md)

本文档记录 github-star-manager 技能的所有变更。

---

## [0.6.0] - 2026-02-28

### 重构（Skill 整合）

| 变更 | 说明 |
|------|------|
| **Skill 整合** | 将 `github-auto-star` 整合到 `github-star-tracker`，统一为 `github-star-manager` |
| **目录重命名** | `github-star-tracker` → `github-star-manager` |
| **模块化设计** | 同一 Skill 包含两个模块：对话模块 + 脚本模块 |

### 新增（对话模块）

| 模块 | 触发方式 | 功能 |
|------|----------|------|
| **对话模块** | 对话触发 | 从内容提取项目并 Star |
| **脚本模块** | 命令行/定时任务 | 同步、Dashboard、追踪、批量管理 |

### 对话模块功能

- 从各种内容来源（URL/截图/文字）中自动提取 GitHub 仓库引用
- 智能匹配：直接匹配 + 按名称搜索 + 上下文相关性验证
- 自动检查是否已 Star，避免重复
- 使用 GitHub CLI (`gh`) 执行 Star 操作

### 删除

- 删除 `github-auto-star` 独立 Skill，功能已整合到 `github-star-manager`

---

## [0.5.1] - 2026-02-14

### 修复（Dashboard UI 问题修复）

| 变更 | 说明 |
|------|------|
| **刷新后默认不显示项目** | 修复默认筛选状态，加载后自动显示项目列表 |
| **标签云不显示** | 修复 `renderTagCloud()` 使用错误的字段，改用 `topics` |
| **Star 时间显示为零** | 修复统计函数未包含 twoyears/threeyears 选项 |
| **时间筛选器不工作** | 修复 `filterProjects()` 使用隐藏 select 而非变量的问题 |

### 增强（时间筛选扩展）

| 变更 | 说明 |
|------|------|
| **新增筛选选项** | 添加"2年"和"3年+"时间筛选选项 |
| **emoji 同步** | 活动标签和 Star 时间的 emoji 保持一致 |
| **默认显示调整** | 将"我的Star时间"设为默认显示标签（左侧） |

### 重构（项目命名）

|  变更  |  说明 |
|--------|--------|
| **项目重命名** | `github-star-tracker` → `github-stars-tracker`（复数形式符合 GitHub 官方命名）|
| **HTML 标题更新** | 页面标题和 H1 标题改为 `GitHub Stars Tracker` |
| **模板文件同步** | 更新 `dashboard.example.html`、`.env.example` 等模板 |

### 模板文件更新

- `assets/dashboard.example.html` - 同步 Dashboard 修复和默认显示
- `assets/.env.example` - 更新标题为 `GitHub Stars Tracker`

---

## [0.5.0] - 2026-02-14

### 新增（数据维度增强 + 双重活跃度筛选）

| 变更 | 说明 |
|------|------|
| **数据字段扩展** | 从 3 个字段扩展到 27 个字段，丰富 AI 分析维度 |
| **starred_at 获取** | 使用认证 API 获取用户 star 的具体时间 |
| **项目更新活跃度筛选** | 按项目更新时间筛选（1周/1月/3月/半年/1年/超1年） |
| **Star 时间筛选** | 按用户 star 的时间筛选，了解近期关注领域 |
| **双维度统计卡片** | 同时显示项目活跃度和 Star 时间分布 |

### 数据字段清单

**基本信息：**
- `full_name`, `name`, `owner`, `html_url`, `description`, `homepage`

**时间维度（关键）：**
- `starred_at` - 用户何时 star 的
- `created_at` - 仓库创建时间
- `updated_at` - 最后更新时间
- `pushed_at` - 最后推送时间
- `local_fetched_at` - 本地抓取时间

**统计数据：**
- `stargazers_count`, `forks_count`, `watchers_count`, `open_issues_count`

**分类信息：**
- `language`, `topics`, `license`, `visibility`

**项目特征：**
- `is_fork`, `is_archived`, `is_template`, `has_wiki`, `has_pages`, `has_discussions`

### 使用示例

```bash
# 重新初始化获取完整数据（27个字段）
python scripts/main.py --init --user cat-xierluo

# 查看 Dashboard（包含活跃度筛选）
open output/dashboard.html
```

### 技术改进

- `save_latest()` 方法重写，保存完整仓库信息
- `get_starred_repos()` 添加 `include_starred_at` 参数，使用 `application/vnd.github.star+json` 获取 starred_at
- Dashboard 添加活跃度统计卡片和筛选下拉框
- JavaScript 添加 `getActivityCategory()` 和 `updateActivityStats()` 函数

---

## [0.4.2] - 2026-02-12

### 新增（输出目录规范）

| 变更 | 说明 |
|------|------|
| **output/ 目录** | 创建专用目录存放运行时生成的文件 |
| **文件组织** | `dashboard.html` 和 `projects.json` 移至 `output/` |
| **gitignore 更新** | 忽略整个 `output/` 目录 |

### 使用说明

运行 `--export` 后，生成的文件位于 `output/` 目录：

- `output/projects.json` - 导出的项目数据
- `output/dashboard.html` - 可视化面板

打开 `output/dashboard.html` 即可查看数据可视化。

---

## [0.4.1] - 2026-02-12

### 修复（目录结构规范化）

- **配置文件散落在根目录** → 移至 `assets/` 目录符合 SKILL-GUIDE.md 规范
- **文档路径引用错误** → 更新 SKILL.md 和 CHANGELOG.md 中的路径

### 变更内容

- 移动 `dashboard.example.html` → `assets/dashboard.example.html`
- 移动 `projects.example.json` → `assets/projects.example.json`
- 移动 `categories.yaml` → `assets/categories.yaml`
- 移动 `tags.json` → `assets/tags.json`
- 更新 `scripts/main.py` 中的模板路径引用
- 更新 `SKILL.md` 配置文件说明

---

## [0.4.0] - 2026-02-12

### 新增（分类与标签系统）

| 功能 | 说明 |
|------|------|
| **分类配置** | `assets/categories.yaml` - 8种预设分类，可自定义 |
| **标签管理** | `assets/tags.json` - 添加、编辑、删除标签 |
| **智能分类** | 根据关键词自动匹配分类（语言/topics/description）|
| **标签云** | Dashboard 顶部显示所有标签，点击筛选 |
| **分类筛选** | 按预设分类（AI/Web/桌面/移动等）筛选项目 |
| **搜索增强** | 支持标签名和关键词搜索 |
| **统计增强** | 显示已分类项目数量 |

### 使用示例

```bash
# 导出数据（现在包含分类和标签）
python scripts/main.py --export

# 编辑分类配置
vim ~/.github-star-tracker/categories.yaml

# 添加新标签
python scripts/main.py --add-tag "游戏引擎" --color "#f472b6"

# 按分类查看
# 然后在 Dashboard 中点击对应分类标签
```

### 技术改进

- 新增 `assets/categories.yaml` 和 `assets/tags.json` 配置文件
- `StarTracker` 添加 `_load_categories()`, `_load_tags()`, `get_categories_map()` 方法
- `StarTracker` 添加 `_match_category()` 方法，根据关键词智能匹配分类
- `get_starred_repos()` 返回的每个仓库包含 `category` 和 `matched_keywords` 字段
- Dashboard 全面重构，支持标签云、分类筛选、搜索

---

## [0.3.1] - 2026-02-12

### 修复

| 问题 | 解决方案 |
|------|----------|
| 只能获取 100 个 Star | 移除 limit 限制，支持分页获取全部 Star |
| 用户名必须手动输入 | 添加 `get_authenticated_user()` 自动获取 Token 对应的用户名 |
| `language=None` 导致崩溃 | 修复空值检查 |
| 符号链接报错 | 修复 `save_snapshot()` 文件覆盖逻辑 |

### 改进

- 默认 limit 从 100 提升到 9999（获取全部）
- Dashboard 修复本地文件加载问题
- `--user` 参数改为可选，未提供时自动获取

---

## [0.3.0] - 2026-02-12

### 新增（Star 管理功能）

| 命令      | 说明                           |
|-----------|------------------------------|
| `--star owner/repo`    | 为单个仓库添加 Star            |
| `--unstar owner/repo`  | 取消单个仓库的 Star           |
| `--cleanup --days 90`   | 查找并清理长期未更新的仓库     |
| `--batch-unstar file.json` | 批量取消 Star（从 JSON 文件） |
| `--batch-star file.json`  | 批量添加 Star（从 JSON 文件）  |

### 使用示例

```bash
# 单个操作
python scripts/main.py --star owner/repo           # 添加 Star
python scripts/main.py --unstar owner/repo        # 取消 Star

# 清理陈旧项目
python scripts/main.py --cleanup --days 90         # 预览（默认）
python scripts/main.py --cleanup --days 90 --execute  # 实际执行

# 批量操作
python scripts/main.py --batch-unstar repos.json   # 批量取消
python scripts/main.py --batch-star repos.json    # 批量添加
```

### 技术改进

- `StarTracker` 类新增 `star_repo()`, `unstar_repo()`, `is_starred()` 等方法
- 添加 `--execute` 安全确认机制，避免误操作
- 所有破坏性操作（取消 Star）默认预览，需要 `--execute` 确认

---

## [0.2.0] - 2026-02-12

### 新增

- **HTML Dashboard**：实现信息密集型可视化面板，支持一屏浏览大量项目
- **数据导出功能**：新增 `--export` 命令，生成 projects.json 供 Dashboard 使用
- **状态筛选**：支持按活跃度（活跃/近期更新/长期未更）和价值（高/中）筛选
- **搜索功能**：支持按项目名、描述、标签进行关键词搜索
- **示例文件机制**：创建 dashboard.example.html 作为模板，首次运行自动复制

### 改进

- 从 knowledge-retention skill 重构，移除社交媒体截图转化功能
- 专注核心功能：更新追踪、版本检测、活跃度分析
- 卡片点击展开详情：显示创建时间、Forks、Issues 等信息

### 技术优化

- 使用 CSS 变量管理主题色值
- 响应式布局，支持移动端浏览
- 本地 JSON 数据缓存，减少 API 请求
