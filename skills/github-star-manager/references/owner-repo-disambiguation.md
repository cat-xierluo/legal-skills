# Owner / Repo 视觉消歧手册

本文件是从截图/OCR/视觉来源提取 GitHub owner/repo 时的消歧规则集。`SKILL.md §2` 只列了最常见的几条启发式，这里给出更全的失败模式与处理动作。

## 何时用本文件

输入是截图/视频帧/图片时，**先**做一遍本文件的视觉消歧检查，再走 `SKILL.md §2` 的同名候选消歧。截图 owner/repo **永远先怀疑 OCR 误读，再怀疑仓库不存在**。

## 规则清单（按出现频率排序）

### 1. 整 owner 完全错读（最常见）

截图直读出的 owner 在 GitHub 上 404 时，先**不**判定"仓库不存在"——按**真实存在的 repo 名做精确搜索**（`gh search repos "repo-name" --limit 10`），用 description 与截图功能描述做语义锚定。

**为什么**：OCR 经常把完整短词错读成完全无关的同长度字符串（sengshiwen ↔ SonghaiFan），但 repo 名通常在描述里高频出现，搜得到。

### 2. 字母形态相似漂移

高风险字母对（视觉/键盘相邻）：

| 错读 | 真身 | 机制 |
|------|------|------|
| `l` ↔ `i` / `I` | oil-oi ↔ oil-oil | 屏幕分辨率低时竖笔划丢失 |
| `f` ↔ `t` | f3knolbox ↔ t3knobox | 字母 f 的横笔划在低 dpi 下糊成 t |
| `ry` ↔ `ey` | whaleryxbt ↔ whaleyxbt | y 的下尾笔划在缩略图里变成 e 的开口 |
| `m` ↔ 漏读起始 | mous-ai ↔ autonomous-ai | 漏读首字母 |
| 数字 `0` ↔ 字母 `o` | 截图 0 实际是 o | 同形异义 |

**动作**：404 时，**对每个 OCR 出的 owner 字符**做一次字母形态替换，生成 2-3 个变体去查。`gh api users/<variant>` 比对返回的 `login` 是否存在。

### 3. owner 前缀/中段缺失

OCR 经常漏读前 1-2 个字符（截断）+漏读中间字母（字距过窄）。**应对**：

- 把 repo 名拿出来做完整搜索（`gh search repos "<repo-name>"`）
- 找到的候选 `full_name` 与截图 owner 拼起来做模糊匹配

### 4. 仓库迁移公告（README 自述 moved-to）

`gh api repos/旧名` 返回 404 时，**先查新仓库的 README/About 字段**——很多项目在 README 头部写明 "Moved to / Archived — moved to github.com/owner/new-name"。

**为什么**：GitHub 旧仓库 archived 后 `gh api` 返回 404，**不是 301**——所以 `SKILL.md §2` 的"改名仓库识别"（依赖 301 重定向）**抓不到**这种 archived+迁移的情况。

**动作**：
```
gh api repos/<旧名>/readme | jq -r '.content' | base64 -d | head -50
```
扫 README 头部找 "moved to" / "relocated to" / "this project has been moved"。

### 5. 截图只露文件夹名而非完整路径

抖音/小红书视频里经常只显示一个**目录/文件名**（`adu-motion-Video/`），不是完整 owner/repo。这种情况：

- 把目录名+功能关键词做 `gh search repos`（如 `"adu-motion-video" "motion"`
- description 里出现截图提到的功能关键词（"动画动效模板 Skill"、"Lottie 动画素材"）的候选优先
- 同时检查候选的 description 与**姊妹项目截图**是否互相印证（截图里出现的另一项目也搜一下，验证同一 owner 拥有两个相关项目）

### 6. 截图中是 README 截图而非 GitHub 仓库页

当截图**是 GitHub README 渲染页**（不是仓库导航页）时，地址栏不可见。**线索源**：

- README 内部**互相引用的项目链接**（如截图提到"基于 Luka 的 mib2q-carplay-rgi 构建"——直接搜 `mib2q-carplay-rgi` 拿 owner，反查主项目 owner）
- **姊妹项目** / "See also" / "Related" 段
- README 内的 build/install 命令（`brew install --cask owner/tap/repo` 这种含 owner 信息的）
- description 与 README 首段的语义匹配

### 7. 多 owner 候选锁定单一

截图里同 owner 名下有多个相关项目（**姊妹套件**、**配套工具**），但只 Star 其中一个可能不够：

- `heygen-com/hyperframes` + `nateherkai/hyperframes-student-kit`（同一主题，学生版）
- `wnby/photo-relic-editorial` + `wnby/paper-spirit-zine`（同一作者的不同 skill）

**动作**：Star 主项目后，**主动列同 owner 名下 description 含相关关键词的其它仓库**，问用户要不要一并 Star，而不是只星主项目就结束。

### 8. 整 token 错读（不只是字符级）

规则 2 只覆盖字符形态漂移（`l`↔`i`、`f`↔`t`）。但 OCR 还会**整词错读**——把功能描述里的一个完整英文 token 替换成另一个语义相近但完全不同的 token。

| 截图 OCR | 真身 | 误读机制 |
|------|------|------|
| `ll-video-motion` | `liuliu-66-create/ll-video-edit` | `motion` ↔ `edit` 语义相近 token 替换 |
| `motion-director` | 是 skill 目录名不是仓库 | token 拼成了独立仓库名 |

**动作**：OCR 报出 token 跟功能描述**语义对不上**时（截图讲"动效素材库"但 OCR 出 `motion`，候选仓库 description 写"自动剪辑 Skill 与视频动效素材库"含 `edit` 也有 `motion`），**用 OCR 词 + 1-2 个近义 token 变体（动效/编辑/剪辑/特效/animation/edit/motion/cut）**分别搜，而不是只搜 OCR 原 token。

### 9. 截图标题是首字母缩写

短视频标题常把项目名压缩成首字母缩写（`LCSC3D` / `dsh-synapse` / `helm-d` / `dsh-zen-remote` / `dsh-boot-animation`），**缩写搜不到完整仓库**：

- 缩写 → 搜 `gh search repos "<缩写>"` 经常 0 命中
- 但同 owner 可能有姊妹项目（`dsh-zen-remote` 跟 `dsh-boot-animation` 都用 `dsh-` 前缀）
- 完整中文名有时反而搜得到（如 `dsh-` 截屏工具是 dsh/desktop-shell 缩写）

**动作**：缩写截图时**先做 owner 候选枚举**（同主题其它项目的 owner 通常重复），再用完整中文名 + 缩写做组合搜索。

### 10. 0 仓库用户（owner 0 public_repos）

`gh api users/<owner>` 返回 200 但 `public_repos: 0` 时，**不要去尝试"猜 repo 名"变体**——这位用户根本没有公开仓库。

**动作**：直接报"owner 存在但 0 公开仓库，截图里 repo 截断无法补全"，列为**待用户补充**而非继续 OCR 变体尝试。

### 11. 跨应用 ID 不通用

截图里的 owner/repo **不是 GitHub ID** 而是其它平台的 ID：

- jlc 嘉立创 OSHWHUB 的 owner 是**嘉立创平台 ID**，GitHub 上没对应用户
- npm 包名、pip 包名、Gitee 用户名同样不通用

**识别信号**：
- 链接域名是 `oshwhub.com` / `npmjs.com` / `gitee.com` / `hub.docker.com`（**不是** `github.com`）
- owner 形如 `kaguyamokou`（拼音短词）/ `xxx-npm` / 带横线连接的 ID

**动作**：**不要用这个 owner 在 GitHub 上搜**——直接报"非 GitHub 平台 ID，GitHub 上无对应仓库"，列为**跳过**而非继续尝试。

### 12. 0⭐ 极小 size 的"刷星壳警告"

当 OCR 出来的 owner/repo 与候选 GitHub 仓库**名字完全一致**（不是 OCR 修正后找到的，是直读就匹配），但同时满足：

- `stargazers_count = 0`
- `size < 100KB`（GitHub API 的 size 字段，KB 单位）
- 提交历史单次 / 几条 commit 全是 "Update README.md"
- 推送时间与仓库创建时间相隔 < 1 小时

→ **高度疑似刷星壳**（创建后没人维护的占位仓库）。

**对比基准**（真 S 级 skill 仓库的 size）：
- `heyimjames/ios-design-skills` 5 个 SKILL.md 总 380KB
- `aora-bot` 几十 MB（含演示资源）

**动作**：
- 名字 100% 匹配 + 0⭐ + size < 100KB → **列候选 + 报告"刷星壳警告"**，不自动 Star，等用户决定
- 名字是 OCR 修正后找到的（说明 OCR 错了）→ 即使 0⭐ 也保留 Star 候选（heyimjames 反例就是这种情况）

### 13. 候选之间的互证（cross-reference）

`gh search repos` 返回多个候选时，**不要只看每个候选本身的 description**——检查**候选之间的 description 是否互相提及**：

- 候选 A description 含 "playing with X by <owner>" → 验证 owner
- 候选 B 是候选 A 的 fork（`isFork: true`）→ 排除
- 候选 C description 含候选 A 的项目名 → 同主题互证

**动作**：拿到候选列表后，**两两交叉读 description**，找互相引用的对子——这比逐个对比截图主题更可靠。

## 完整消歧流程（截图输入专用）

```
[截图] → 1. 视觉分析抽 owner/repo
       → 2. 4 个最常见误读立刻套：l/i、f/t、0/o、前缀缺失
       → 3. 查重 `gh api user/starred/<ocr-owner>/<ocr-repo>` (HTTP 204/404)
       → 4. 若 404，按以下顺序尝试：
           a. OCR 字符形态替换生成 2-3 个变体 owner
           b. 按 repo 名精确搜 `gh search repos "<repo-name>"`
           c. 搜 README "moved to" 公告
           d. 用截图功能描述 + repo 名做组合搜索
       → 5. 找到候选后，做语义锚定（description ↔ 截图功能）
       → 6. 跨引用验证：截图里提到的姊妹项目/作者也搜一遍，验证 owner 互引
       → 7. 命中单一候选 → 查重+PUT+回读
       → 8. 多候选 → 列给用户确认（不要凭 star 数 alone 决定）
```

## 不要做的事

- **不要**：OCR owner 404 就宣布"找不到"，跳过 Star
- **不要**：用 star 数量级作为单一证据，绕过语义锚定
- **不要**：跳过"完整消歧流程"中的姊妹项目互引步骤（这是低成本高收益的二次确认）
- **不要**：把"框架本身"（Remotion / Lottie / GSAP / FFMpeg）和 skill 仓库混在一起 Star——按 `SKILL.md §2` 的"衍生仓库排除"规则处理
