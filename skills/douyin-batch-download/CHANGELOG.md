# 变更日志

> 本技能的所有变更记录，按时间倒序排列。

---

## [1.8.0] - 2026-02-14: 脚本架构优化与废弃清理

**类型**：🔧 重构
**描述**：统一数据获取方式为 F2 API，废弃浏览器方式抓取，修复 aweme_id 提取逻辑

**变更文件**：

- `scripts/batch-download.py` - 改用 download-v2.py
- `scripts/download.py` - 标记为废弃
- `scripts/extract-metadata.py` - 标记 --fetch 为废弃，修复 aweme_id 提取
- `scripts/generate-data.py` - 修复 aweme_id 提取逻辑
- `SKILL.md` - 更新文档

**核心变更**：

1. **数据获取方式统一**
   - 所有数据抓取统一使用 F2 API
   - 浏览器仅用于 Cookie 管理（登录/更新）
   - 废弃 `extract-metadata.py --fetch` 选项

2. **脚本废弃标记**
   - `download.py` → 推荐使用 `download-v2.py`
   - `--fetch` 选项 → 推荐重新下载视频（自动保存统计数据）

3. **aweme_id 提取修复**
   - 修复文件名中包含下划线时 aweme_id 提取错误的问题
   - 新逻辑：找出所有 15 位以上纯数字段，返回最长的那个

**推荐工作流**：

```bash
# 单个博主下载（推荐）
python scripts/download-v2.py "https://www.douyin.com/user/MS4wLjABAAAA..."

# 批量下载
python scripts/batch-download.py --all

# 采样下载（快速更新数据）
python scripts/batch-download.py --sample
```

---

## [1.7.0] - 2026-02-14: Web 界面交互重构

**类型**：🎯 交互重构
**描述**：重构 Web 界面交互设计，采用二级页面架构，优化视频浏览体验

**变更文件**：

- `downloads/index.html` - 完全重构为二级页面架构

**新交互设计**：

```
┌─ 主页面 ─────────────────────────────────────┐
│  抖音视频库                                   │
│  20 博主  95 视频  共 4.0GB                   │
├────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐          │
│  │ 👤 头像       │  │ 👤 头像       │          │
│  │ 博主A         │  │ 博主B         │          │
│  │ 10视频 50MB   │  │ 25视频 200MB  │          │
│  │ ❤️ 1.2万       │  │ ❤️ 5000       │          │
│  └──────────────┘  └──────────────┘          │
│         点击进入详情页                         │
└────────────────────────────────────────────────┘

┌─ 详情页（二级页面）────────────────────────────┐
│  ← 返回  👤 博主A   访问主页 →                  │
│         10 视频  50MB  ❤️ 1.2万                │
├────────────────────────────────────────────────┤
│  共 10 个视频    [点赞][时间][大小][评论][收藏] │
├────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐     │
│  │ 视频1    │  │ 视频2    │  │ 视频3    │     │
│  │ ❤️ 5000   │  │ ❤️ 3000   │  │ ❤️ 2000   │     │
│  │ 5MB     │  │ 8MB     │  │ 6MB     │     │
│  └──────────┘  └──────────┘  └──────────┘     │
└────────────────────────────────────────────────┘
```

**核心改进**：

1. **二级页面架构**
   - 主页面：两列展示博主卡片，简洁清爽
   - 详情页：全屏展示博主的所有视频
   - 页面切换：滑入动画，ESC 键返回

2. **博主卡片**
   - 显示头像（点击跳转抖音主页）
   - 显示视频数、占用空间、互动数据
   - 两列网格布局

3. **视频排序**
   - 支持按点赞、时间、大小、评论、收藏排序
   - 排序状态持久化

4. **视频播放**
   - 点击视频卡片打开播放模态框
   - 显示视频标题和统计数据
   - ESC 键或点击背景关闭

**交互流程**：

```
1. 主页面浏览博主列表
2. 点击博主卡片 → 滑入详情页
3. 详情页查看所有视频（可排序）
4. 点击视频 → 打开播放模态框
5. 点击返回按钮或 ESC → 返回主页面
```

**视觉优化**：

- 简约风格：浅色背景 + 白色卡片 + 蓝色强调色
- 微妙动画：页面滑入、悬停效果
- 清晰层次：信息分组明确

---

## [1.6.0] - 2026-02-13: 采样下载 + 目录结构优化

**类型**：🔧 功能增强
**描述**：新增采样下载模式，优化脚本目录结构

**新增功能**：

- 新增 `--sample` 参数：每个博主只下载 1 个视频，用于快速更新数据而不占用大量空间
- 新增 `--yes` 参数：跳过确认步骤，适合自动化脚本
- `download.py` 支持 `--max-counts=N` 参数控制下载数量

**目录优化**：

- 将 `scripts/helpers/following.py` 移至 `scripts/following.py`（消除二级目录）
- 移除不再需要的 `sys.path` 配置
- 更新所有导入语句

**使用示例**：

```bash
# 采样下载（每个博主1个视频）
python scripts/batch-download.py --sample --yes

# 全量下载
python scripts/batch-download.py --all --yes

# 交互选择
python scripts/batch-download.py

# 指定博主下载（最多3个视频）
python scripts/download.py "https://www.douyin.com/user/xxx" --max-counts=3
```

**变更文件**：

- `scripts/batch-download.py` - 新增 --sample 和 --yes 参数
- `scripts/download.py` - 支持 --max-counts 参数
- `scripts/following.py` - 从 helpers 目录移至 scripts 目录
- `scripts/manage-following.py` - 更新导入语句
- `scripts/sync-following.py` - 更新导入语句

---

## [1.5.0] - 2026-02-12: Accordion 交互重构

**类型**：🎯 交互重构
**描述**：移除独立标签页，改为点击博主卡片展开/折叠视频列表的 Accordion 模式

**变更文件**：

- `downloads/index.html` - 完全重构为 Accordion 交互设计

**新交互设计**：

```
┌────────────────────────────────────┐
│  抖音视频库                    [搜索框]    │
├────────────────────────────────────┤
│                                        │
│  ┌─────────┐  ┌─────────┐  │
│  │ 博主A  │  │ 博主B  │  │
│  │ 10视频  │  │ 25视频   │  │
│  └────────┘  └────────┘  │
│       ▼                ▼          │
│  ┌──────────────────┐     │
│  │ 视频1.mp4      │     │
│  │ 视频2.mp4      │     │
│  │ ...            │     │
│  └──────────────────┘     │
│                                │
└────────────────────────────────────┘
```

**交互逻辑**：

1. 点击博主卡片 → 在下方展开显示该博主的视频列表
2. 再次点击 → 折叠视频列表
3. 可同时展开多个博主（方便对比不同博主的内容）
4. 搜索支持过滤博主或视频

**视觉升级**：

- 标题字号增大：2rem（原1.25rem）
- 展开/折叠动画：平滑过渡效果
- 展开指示器：箭头图标旋转 180°
- 字体更换：Noto Sans SC（更优雅的中文显示）
- 配色优化：电光蓝 (#5b7fff) 强调色

---

## [1.4.4] - 2026-02-12: Glassmorphism UI 设计

**类型**：✨ 视觉升级
**描述**：采用 Glassmorphism（毛玻璃）设计语言，打造独特的视觉体验

**变更文件**：

- `downloads/index.html` - 完全重构 CSS 和布局

**设计特点**：

- **动态背景**：深蓝灰渐变 + 漂浮的光晕效果
- **毛玻璃卡片**：半透明背景 + 背景模糊
- **优雅动效**：入场动画、悬停效果、光晕发光
- **现代字体**：Inter 字体 + JetBrains Mono 等宽字体
- **精致细节**：噪点纹理、渐边框、圆角设计

**配色方案**：

```css
背景: #0d0d12 → #1a1a2e → #0f0f1a (深蓝灰渐变)
卡片: rgba(255, 255, 255, 0.05) → 0.08 (悬停)
强调色: #4a90e2 (电光蓝)
光晕: rgba(74, 144, 226, 0.3)
```

**视觉升级**：

- 标题采用渐变文字效果
- 统计信息使用胶囊样式 + 等宽字体
- 标签页悬停显示毛玻璃效果
- 用户卡片增大头像尺寸 (44px) + 渐边框
- 视频图标采用渐变背景 + 投影效果
- 所有空状态添加图标提示

---

## [1.4.3] - 2026-02-12: Web 界面简化

**类型**：🔧 重构
**描述**：简化 Web 界面，采用纯静态数据加载方式（参考本地库.html）

**变更文件**：

- `downloads/index.html` - 完全重写，去掉 File System Access API
- `scripts/generate-data.py` - 修改输出格式为 .js 文件
- `scripts/download.py` - 下载完成后自动生成数据文件

**新方案**：

采用**纯静态 JavaScript 数据文件**架构：

```text
用户操作流程：
1. 运行 python scripts/download.py <URL> → 下载完成后自动生成 data.js
2. 双击 index.html → 直接加载使用
```

**核心优势**：

- 双击即可打开，无需任何服务器
- 无需手动选择文件/目录
- 下载完成后自动更新数据
- 压缩后手动运行 `generate-data.py` 即可
- 浏览器兼容性最佳（所有现代浏览器）

**使用方法**：

```bash
# 下载（完成后自动生成数据）
python scripts/download.py "https://www.douyin.com/user/xxx"

# 直接用浏览器打开 index.html（或双击文件）
open /Users/maoking/Library/Application\\ Support/maoscripts/skills/legal-skills/test/douyin-batch-download/downloads/index.html
```

---

## [1.4.2] - 2026-02-12: 压缩功能优化

**类型**：🔧 重构
**描述**：简化 Web 界面，采用纯静态数据加载方式（参考本地库.html）

**变更文件**：

- `downloads/index.html` - 完全重写，去掉 File System Access API
- `scripts/generate-data.py` - 修改输出格式为 .js 文件

**新方案**：

采用**纯静态 JavaScript 数据文件**架构：

```text
用户操作流程：
1. 运行 python scripts/generate-data.py → 生成 data.js
2. 双击 index.html → 直接加载使用
```

**核心优势**：

- 双击即可打开，无需任何服务器
- 无需手动选择文件/目录
- 压缩后重新生成 data.js 即可
- 浏览器兼容性最佳（所有现代浏览器）

**使用方法**：

```bash
# 1. 生成数据文件
python scripts/generate-data.py

# 2. 直接用浏览器打开 index.html（或双击文件）
open /Users/maoking/Library/Application\\ Support/maoscripts/skills/legal-skills/test/douyin-batch-download/downloads/index.html
```

---

## [1.4.2] - 2026-02-12: Web 界面修复

**类型**：🐛 Bug 修复
**描述**：修复 index.html 无法动态更新的问题，采用纯前端 File System Access API 方案

**变更文件**：

- `downloads/index.html` - 重写为纯前端实现

**问题分析**：

- `downloads/index.html` - 重写为纯前端实现

**问题分析**：

原方案存在以下问题：
1. 硬编码的文件路径无法通过 `fetch()` 访问（浏览器安全限制）
2. 静态数据无法反映压缩后的文件变化

**新方案**：

采用**纯前端 File System Access API**架构：

```text
用户操作流程：
1. 点击 "选择 following.json" → 选择配置文件
2. 点击 "选择 downloads 目录" → 选择视频目录
3. 点击 "刷新数据" → 重新扫描文件系统
```

**使用方法**：

```bash
# 直接用浏览器打开 index.html（无需服务器）
open /Users/maoking/Library/Application\ Support/maoscripts/skills/legal-skills/test/douyin-batch-download/downloads/index.html

# 或者双击文件打开
```

**功能**：

- 📁 选择 following.json - 读取博主配置
- 📁 选择 downloads 目录 - 扫描视频文件
- 🔄 刷新数据 - 重新加载（压缩后点击）
- 博主列表视图 - 展示所有已下载的博主
- 视频网格视图 - 展示所有下载的视频
- 点击博主卡片可查看该用户的视频
- 搜索过滤 - 实时搜索博主或视频
- 统计信息 - 博主数、视频数、占用空间

**浏览器兼容性**：

- Chrome/Edge 86+：完整支持
- Firefox 103+：支持
- Safari：部分支持（需要用户测试）

**使用方法**：

```bash
# 启动本地 Web 服务器
cd /Users/maoking/Library/Application\ Support/maoscripts/skills/legal-skills/test/douyin-batch-download
python downloads/server.py

# 然后在浏览器打开
open http://localhost:8000
```

**功能**：

- 博主列表视图 - 展示所有已下载的博主
- 视频网格视图 - 展示所有下载的视频
- 点击博主卡片可查看该用户的视频
- 搜索过滤 - 实时搜索博主或视频
- 统计信息 - 博主数、视频数、占用空间
- 刷新按钮 - 重新加载数据（压缩后点击刷新即可看到更新）

---

## [1.4.1] - 2026-02-12: 压缩功能优化

---

## [1.4.0] - 2026-02-12: 新增视频压缩功能

**类型**：✨ 功能增强
**描述**：新增视频压缩脚本，使用 ffmpeg 对下载的视频进行压缩，节省存储空间

**变更文件**：

- `scripts/compress.py` - 新增视频压缩脚本
- `config/config.yaml.example` - 新增压缩配置选项
- `SKILL.md` - 更新文档，添加压缩功能说明

**功能**：

- `scripts/compress.py` - 视频压缩脚本
  - 支持压缩全部视频或指定用户视频
  - 支持压缩单个视频文件
  - 默认直接替换原文件（节省空间）
  - 可选保留原文件（使用 `--keep`）
  - 可配置压缩质量 (CRF) 和速度预设
  - 智能跳过小文件（<5MB，避免压缩后变大）
  - 显示压缩率和文件大小变化
  - 自动跳过已压缩的视频

**配置选项**：

```yaml
compression:
  auto_compress: false       # 是否在下载后自动压缩
  crf: 32                  # 压缩质量 (0-51, 默认32, 推荐28-38)
  preset: "fast"            # 压缩速度预设
  replace_original: true      # 压缩后是否替换原文件 (默认true)
  skip_small_threshold: 5242880  # 小文件阈值 (5MB)
```

**使用示例**：

```bash
# 压缩全部视频（默认直接替换原文件）
python scripts/compress.py

# 压缩指定用户视频
python scripts/compress.py --user 123456789

# 压缩单个视频文件
python scripts/compress.py --file video.mp4

# 保留原文件（生成 xxx_compressed.mp4）
python scripts/compress.py --keep

# 设置更高的压缩率
python scripts/compress.py --crf 38

# 不跳过小文件
python scripts/compress.py --no-skip-small
```

**依赖**：

- 需要 ffmpeg 系统，压缩功能可选

---

## [1.3.2] - 2026-02-12: 数据源重构 + Web 管理界面 + 链接解析

**类型**：🔧 重构 + ✨ 功能增强
**描述**：重构数据源，以 F2 缓存为主，新增 Web 管理界面、链接解析、last_fetch_time 追踪

**变更文件**：

- `scripts/sync-following.py` - 重构为从 douyin_users.db 同步
- `downloads/index.html` - 新增 Web 管理界面
- `scripts/reorganize.py` - 新增文件整理脚本
- `scripts/parse-link.py` - 新增链接解析脚本

**数据源设计**：

```text
douyin_users.db (F2 缓存) → following.json (用户关注列表)
                              ↓
                         index.html (Web 管理)
```

| 文件 | 定位 | 用途 |
| :--- | :--- | :--- |
| `douyin_users.db` | F2 内部缓存 | 技术数据源，用户信息 |
| `following.json` | 用户关注列表 | 业务数据源，可手动编辑 |
| `downloads/` | 视频文件 | 本地存储 |

**功能**：

- `sync-following.py`
  - 从 F2 数据库同步用户信息到 following.json
  - 保留 last_fetch_time 等自定义字段
  - 更新 following.json 的 last_fetch_time
- `downloads/index.html` - Web 管理界面
  - 博主列表视图 - 展示已下载的所有博主
  - 视频网格视图 - 展示所有下载的视频
  - 搜索过滤 - 按名称搜索博主或视频
- `scripts/parse-link.py` - 链接解析脚本
  - 从任意文本中提取抖音链接
  - 支持 `https://v.douyin.com/xxx` 短链接

**使用示例**：

```bash
# 下载并更新 last_fetch_time
python scripts/download.py "https://v.douyin.com/xxx"

# 从包含链接的文本中提取并下载
python scripts/parse-link.py "8- 长按复制此条消息... https://v.douyin.com/NX0YA7r0NXg/"
```

**following.json 结构**：

```json
{
  "2722012335188296": {
    "uid": "2722012335188296",
    "sec_user_id": "...",
    "name": "张总聊信任",
    "last_fetch_time": "2026-02-12T...",  // 自动更新
    "video_count": 20
  }
}
```

---

## [1.3.1] - 2026-02-12: following.json 同步功能完善

**类型**：✨ 功能增强
**描述**：新增统一下载脚本，自动整理文件结构，统一使用 uid 作为标识

**变更文件**：

- `scripts/download.py` - 新增统一下载脚本
- `scripts/sync-following.py` - 新增关注列表同步脚本

**功能**：

- `scripts/download.py` - 一键下载脚本
  - 使用 F2 CLI 下载视频
  - 自动整理文件到 `downloads/{uid}/`
  - 自动同步 following.json
- `scripts/sync-following.py` - 同步关注列表
  - 从 `downloads` 目录扫描已下载的博主
  - 自动从 F2 数据库获取用户详细信息
  - 同步更新 `config/following.json`

**目录结构**：

```text
downloads/
└── {uid}/           # 使用纯数字 uid 作为文件夹名
    └── *.mp4
```

---

## [1.3.0] - 2026-02-12: 文档重构与依赖说明完善

**类型**：📝 文档重构
**描述**：重构文档结构，将详细依赖和使用说明移到 references 目录，简化 SKILL.md

**变更文件**：

- 新增 `references/INSTALLATION.md` - 详细依赖文档
- 新增 `references/USAGE.md` - 详细使用说明
- `SKILL.md` - 添加依赖章节，简化内容
- `README.md` - 已删除（内容迁移到 references）

**重构内容**：

- 遵循 Progressive Disclosure 设计原则
- SKILL.md 只保留核心信息和快速开始
- 详细依赖说明移至 references/INSTALLATION.md
- 详细使用说明移至 references/USAGE.md

---

## [1.2.5] - 2026-02-12: 页面导航与持久化功能修复

**类型**：🐛 Bug 修复
**描述**：修复登录脚本无法自动导航到抖音网站的问题

**变更文件**：

- `scripts/login.py` - 添加页面对象获取和网站导航逻辑

**修复内容**：

- 修复缺失的页面对象获取（持久化模式使用 `context.pages[0]`，普通模式创建新页面）
- 添加 `await page.goto()` 导航到抖音首页
- 验证持久化功能：首次扫码，后续自动使用已保存登录状态

---

## [1.2.4] - 2026-02-12: 登录检测逻辑修复

**类型**：🐛 Bug 修复
**描述**：修复登录脚本误判问题，改用 cookie 检测代替 URL 检测

**变更文件**：

- `scripts/login.py` - 修复登录检测逻辑和配置文件路径

**修复内容**：

- 修复配置文件路径解析（`parent.parent` 回到根目录）
- 改用登录特征 cookie 检测（`sessionid`、`passport_csrf_token` 等）
- 添加进度提示，每 5 秒显示等待状态
- 修复 URL 误判导致无法扫码的问题

---

## [1.2.3] - 2026-02-12: 登录脚本整理与 Bug 修复

**类型**：🔧 重构 + 🐛 Bug 修复
**描述**：合并重复的登录脚本，修复代码结构问题

**变更文件**：

- `scripts/login.py` - 保留精简版，删除冗余版本
- `scripts/login-simple.py` - 已删除（合并到 login.py）
- `README.md` - 更新命令引用

**修复内容**：

- 删除重复的登录脚本，只保留一个维护入口
- 修复 `async with` 块缩进错误（cookies 获取位置错误）
- 移除未使用的 `playwright_instance` 变量
- 浏览器关闭逻辑优化

---

## [1.2.2] - 2026-02-12: 扫码登录脚本重构

**类型**：🔧 重构
**描述**：将登录脚本重构为精简版本，只负责打开浏览器和获取 cookies

**变更文件**：

- `scripts/login-simple.py` - 精简版扫码登录脚本
- `README.md` - 更新命令引用

**重构内容**：

- 移除登录按钮点击逻辑（应在下载脚本处理）
- 移除头像检测逻辑（应在下载脚本处理）
- 移除不必要的等待和调试代码
- 只保留核心功能：打开浏览器 + 等待登录 + 获取 cookies
- 简化异常处理流程

---

## [1.2.1] - 2026-02-12: 添加扫码登录功能

## [1.2.1] - 2026-02-12: 扫码登录调试优化

**类型**：🐛 调试优化
**描述**：修复 Playwright API 参数问题，添加详细调试日志，提升脚本稳定性

**变更文件**：

- `scripts/login.py` - 扫码登录脚本

**修复**：

- 修复 `query_selector()` timeout 参数错误
- 延长页面加载超时时到 60 秒
- 添加 `wait_until="domcontentloaded"` 等待 DOM 完全加载
- 添加页面标题获取用于调试
- 添加详细状态日志输出
- 添加完整异常堆栈跟踪

---

## [1.2.0] - 2026-02-12: 添加扫码登录功能

**类型**：✨ 功能增强
**描述**：添加扫码登录工具，自动获取抖音登录态 cookies，避免手动复制

**变更文件**：

- `scripts/login.py` - 扫码登录脚本

**功能**：

- 打开浏览器显示抖音登录二维码
- 用户扫码后自动获取 cookies
- 自动保存到配置文件
- 输出 cookies 字符串供复制使用

---

## [1.1.0] - 2026-02-12: 添加 Web 管理界面

**类型**：✨ 功能增强
**描述**：添加轻量级 HTML 界面，支持浏览和搜索已下载的视频

**变更文件**：

- `index.html` - Web 管理界面（纯静态，无需后端）
- `config/following.json.example` - 关注列表模板
- `README.md` - 添加 Web 界面使用说明

**功能**：

- 博主列表视图 - 展示已下载的所有博主
- 视频网格视图 - 展示所有下载的视频
- 搜索过滤 - 按名称搜索博主或视频
- 统计信息 - 显示博主数量、视频总数、占用空间

---

## [1.0.0] - 2026-02-11: 技能创建

**类型**：📦 新技能
**描述**：创建抖音视频批量下载 skill，包含完整的目录结构、配置管理、F2 框架集成

**变更文件**：

- `SKILL.md` - 技能定义文档
- `TASKS.md` - 任务清单
- `DECISIONS.md` - 决策记录
- `README.md` - 使用说明
- `LICENSE.txt` - MIT 许可证
- `scripts/download.py` - 基于 F2 的下载脚本
- `config/config.yaml.example` - 配置模板

---
