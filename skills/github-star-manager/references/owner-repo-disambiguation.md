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
