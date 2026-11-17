# 截图来源：从照片库批量找项目、Star 与清理源图

> 适用：用户说「看看我最近的截图里有哪些可以 star 的」「从截图里找项目并 star」「处理完把源图删掉」，且来源是 **Mac 照片库**（iPhone 截图经 iCloud 同步）而非单张附图。
>
> 分工：mac-photos 技能负责图库读取、OCR 索引、搜索与标记删除；本流程只负责把「截图 → 仓库 → star → 清理」编排成可交付结果，并守住授权边界与删除集合边界。

## 0. 三层授权边界（动手前先定权限）

| 层级 | 用户典型说法 | 可做 | 不可做 |
|---|---|---|---|
| 只发现 | 「看看最近的截图里有哪些可以 star 的」 | 建索引、检索、列出候选仓库、给建议清单 | 标记、删除、prune、改索引状态 |
| 已授权 star | 「从截图里找项目并 star」 | 核实仓库并 star（查重 → PUT → 回读） | 删除源图（star 授权不含删除授权） |
| 已授权删除 | 「star 完把源图删掉」「把这批截图清理掉」 | 按第 4 节进入删除流程 | 删除本次授权范围之外的任何截图 |

- 三个层级独立成立：**star 授权 ≠ 删除授权**；用户点了系统确认框 ≠ 事先对具体源图的业务授权。
- 只有用户**明确说要删**才进入第 4 节；只说「star」「看看」就停在结果与候选清单。
- 用户已给出的授权不再重复追问；授权范围含糊（「把那些删了」「清理一下」）先核对具体对象，不按猜测删。
- 即使有删除授权，也只处理**本次授权范围内、且已核实对应关系**的源图；待确认、未找到对应仓库、用户自己标了保留的截图一律留下。

## 0.1 执行环境：脚本在 mac-photos 目录，不在本 Skill

`photos_read.py` 属于 **mac-photos** 技能，本 Skill 目录下没有 `scripts/photos_read.py`；在本 Skill 目录直接跑 `python3 scripts/photos_read.py` 必然报文件不存在。

1. **先读 mac-photos 的现行 SKILL.md**：命令、参数、权限与行为以那份为准。本流程引用的是它的实际能力边界，不是想当然的版本。
2. **从 mac-photos 的实际安装目录执行**（用它的真实路径，别假定在本 Skill 内）。安装位置按实际发现取（本机为 `~/.agents/skills/mac-photos`，是符号链接，真实路径在私仓），先确认再调用：

   ```bash
   mac_photos_dir="$HOME/.agents/skills/mac-photos"   # 以实际为准
   cd "$mac_photos_dir" && python3 scripts/photos_read.py doctor
   ```

3. 也可以用绝对路径调用，避免工作目录歧义：`python3 "$mac_photos_dir/scripts/photos_read.py" stats`。
4. **索引与工作区位置**（默认值）：`~/Pictures/PhotosReader/index.jsonl`（索引）、`~/Pictures/PhotosReader/exports/`（导出图）。用 `--workspace` 可改；读之前先确认它就是本轮该用的那一份。

## 0.2 范围对齐与自检

1. **先量范围**：`python3 scripts/photos_read.py stats` 看索引规模、最新日期与各状态计数（待删 / 保留 / 已删）；用户没给范围时默认「近 30 天」，并把范围的确定结果写进报告。
2. **自检**：`doctor` 五项全绿再开始（完全磁盘访问、osxphotos、OCR 工具、OCR 冒烟、索引）。
3. **补索引默认用 `--preview-only`**：`scan --preview-only` 只用本地预览图，不触发 iCloud 原片下载，也就不需要「照片」权限；`scan` 默认会补齐原片（需「照片」权限，产生实际下载与流量）。用户没要求高清原图就一律 preview-only：

   ```bash
   python3 scripts/photos_read.py scan --preview-only --from-date 2026-10-18
   ```

4. **单张补读**：索引里没有的新图，先用上面的 `scan --preview-only` 走 mac-photos 自己的路径入索引。仍需单独导出预览时，用它实际调用的 osxphotos（`$OSXPHOTOS_BIN`，缺省 `~/venvs/osxphotos/bin/osxphotos`），并显式带上图库与预览参数。`$UUID` 取索引里的完整 uuid，`$EXPORTED_FILE` 取 export 实际产出的文件名（两者都先设成真实值再执行）：

   ```bash
   UUID="从索引复制的完整UUID"
   EXPORTED_FILE="export 实际产出的文件名"
   "$OSXPHOTOS_BIN" --library "$HOME/Pictures/Photos Library.photoslibrary" \
     export /tmp/gm-screenshot-pick --uuid "$UUID" --preview-if-missing
   python3 "$mac_photos_dir/scripts/bin/ocr-vision" "/tmp/gm-screenshot-pick/$EXPORTED_FILE"
   ```

   OCR 结果只作为本轮证据写进报告；**索引条目由 mac-photos 的 scan 路径维护，不手工写 index.jsonl**。
5. **未命中不要直接说「没有」**：说明已查范围（日期窗口、索引张数、排除规则）再下结论。索引为空，与「有截图但 OCR 没识别出关键词」是两回事，要分开说。

## 1. 摄取与线索提取

- 列出范围记录（date / uuid / status / text / links / github / github_guess），先看机器提取的完整 `github.com/owner/repo`——最可靠。
- 短链接候选（`github_guess`）必须语义复核后再采信；截图 OCR 的 owner/repo 先怀疑误读，按 [`owner-repo-disambiguation.md`](owner-repo-disambiguation.md) 处理。
- 无链接但功能描述清晰（「我手搓的动效 Skill」「批量剪辑模板」）时，按功能 + 技术指纹搜索，不要放弃。
- 实拍照片（带相机 EXIF）不属于信息图集，排除；Live Photo 视频部分无文字价值，跳过。

## 2. 仓库核实与分级

逐个候选仓库：

- 存在性 + 元数据：`gh api repos/<owner>/<repo>`（description / stars / fork / archived / pushed_at / license）。
- **排除干扰**：同名搬运版、社区 fork、学术同名项目；排除要留理由（语言、star 量级、发布日期、目录结构）。
- **内容指纹**：候选的 README/SKILL.md 关键句（触发词、工作流、依赖）须与截图语境吻合。判定分三种，不许混：
  - **确认不符**：已取得可比内容，且候选内容与截图展示的指纹明确冲突 → 不是同一个，不 star。实测：同名 `motion-design-prompt-generator` 仓库 SKILL.md 无截图展示的 Priority order/motion.ts 指纹，判为不同项目。
  - **取不到指纹**：截图没展示对应文件、候选仓库未取证或取证失败 → **不能判为不同**，记「待确认」并写清还缺什么。
  - **一致**：指纹吻合 → 可 star。
- **早已 star 核对**：`gh api user/starred/<owner>/<repo>`，用户常自己先 star 过——清单「已 star 跳过」单列，不能报成新增。
- 分级产出：**建议 star / 值得再看 / 存疑排除 / 已 star**，每项带来源截图日期。

## 3. Star 执行

```bash
gh api user/starred/owner/repo        # 查重：204 已 star / 404 未 star
gh api -X PUT user/starred/owner/repo # star（幂等）
gh api user/starred/owner/repo        # 回读 204 才算成功
```

- 失败等 3–5 秒重试一次再回读；瞬时抖动常见，不要急着判 FAIL。
- `gh api` 返回 `invalid character '<'` 之类是网关错误页，重试即可。
- 批量时单个失败不阻断其余；最后按汇总报告。

## 4. 清理源图（**仅在有明确删除授权时进入**）

前置：本节只在第 0 节判定为「已授权删除」时执行。没有授权就整节跳过，报告只写发现与候选清单。

### 4.1 先冻结授权集合与原状态

- **uuid 一律从索引按内容取**：脚本里 `load_index()` 后按文本/日期匹配置信 uuid，绝不手抄——抄错一位会删错或删不到（实测两次翻车）。
- 标记前先读出每张待处理图的**完整 uuid + 原状态**（`status`：空/`active`/`to_delete`/`keep`/`deleted`），连同来源截图日期列成本轮冻结清单。
- 冻结清单只含本次授权范围内、已核实对应关系的图；待确认、未找到对应仓库的不进清单。

### 4.2 `keep` 是保护标记，默认排除

- mac-photos 的 `mark --delete` **无条件覆盖**目标记录的状态（它的取值只排除已 `deleted` 的记录），不会替你保住 `keep`；一旦被覆盖，后续 prune 会选中它。
- 所以标记前必须逐项核对原状态：**`keep` 默认排除**，不进待删集合。
- 用户明确要删某张 `keep` 图时，单独披露这一项（哪个 uuid、原本有保护标记）并取得该项授权后再改；不得连带处理同批其他 `keep` 项。

### 4.3 干跑与集合一致（逐 uuid 对账，不看张数）

- mac-photos 的 `prune` 每次调用都**重新读取全部 `to_delete`**；干跑只展示前 20 条的日期和首行文字（且不含 uuid），`--execute` 会把**当时全部待删目标**交给删除器。张数相同不等于集合相同——别人替换掉某个 uuid，张数检查发现不了。
- 因此：
  1. 干跑时同时导出**完整待删集合**（全部 uuid + 原状态 + 日期），与本轮授权集合**逐 uuid 对账**。`prune` 干跑打印不全，用只读方式从索引取全量（不要改它）：

     ```bash
     python3 -c 'import json,os;[print(r["uuid"], r.get("date","")[:10], r.get("file","")) for r in map(json.loads, open(os.path.expanduser("~/Pictures/PhotosReader/index.jsonl"), encoding="utf-8")) if r.get("status")=="to_delete"]'
     ```

  2. **不属于本次授权的待删项保留，不得进入本轮删除**。
  3. 执行前重新读一次待删集合，与干跑集合**逐 uuid 比较**；有任何增删或替换，立即停止、重做预览并重新对账。
  4. 系统确认框弹出前提醒用户点「允许」；确认框里的张数与冻结清单不一致时取消，不要点。

### 4.4 删除单位是「整个待删队列」——mac-photos 没有精确到 uuid 的删除入口

- 现状核实：`prune`（CLI）与 `serve` 页面的批量删除都以**整个 `to_delete` 队列**为单位，没有「只删这几个 uuid」的参数或接口。
- 因此只有一种情况可以由本流程执行 prune：**当前整个待删集合与本轮授权集合逐 uuid 完全一致**（队列里没有其他会话或早先任务留下的待删项），此时集合一致由 4.3 的对账保证。
- 队列里**混入**任何不属于本次授权的待删项时：
  - **不运行 prune**（它会连同越权项一起删）；
  - 不去清掉、也不去改写那些越权项的状态（那是共享索引上的他人标记，`mark --active` 同样是直接改写索引）；
  - 输出**待审删除清单**：完整 uuid、日期、原状态、来源截图、理由，交给用户或 mac-photos 原工具执行；
  - 报告里写明：本轮未执行删除、待审清单去向、哪些项因不在授权范围而保留。
- 不声称本流程具备按 uuid 精确删除的能力，也不指示对整个队列执行 prune。

### 4.5 索引与图库失同步：只认删除回执

- `osxphotos query --uuid <u>` 查不到**不等于**已删除：图库选错、访问权限不足、查询失败、条目未同步、本地标识形态不匹配，都可能造成空结果。**一次空结果不构成删除证据**。
- 结算为「已删」需要以下之一：
  - mac-photos 删除流程返回的**可验证回执**（prune 成功结果里列出的 uuid 集合）；或
  - 核对了图库身份（`--library` 指向实际图库）、确认查询成功且权限正常、uuid 完整，并另有独立的删除证据。
- mac-photos 的 `prune` 只把**自己成功删掉**的 uuid 写成 `deleted`（文字档案保留，仍可按内容搜索）；失败的保持 `to_delete` 并给出错误原因。
- mac-photos 当前**没有**「按 uuid 单独同步索引状态」的入口。**不要手工改 `index.jsonl`**（共享索引，直接改会破坏其他会话的状态账本）。无受支持的同步入口时：保留差异、如实报告（哪几个 uuid 状态存疑、缺什么证据），把处置交回 mac-photos 原工具或用户。
- 用户可能同时在相册页面自行删除：这类差异同样按「只认回执」处理，查不到就标待核，不替用户改索引。

## 5. 清单文件与报告

- 清单落 `$CLAWD_REPORTS`（`folder_rules.py suggest` 解析），按轮次追加：日期-来源截图-处置-理由；追加后检查**没有顶掉已有标题或打乱段落顺序**（实测踩过）。
- 每轮报告固定栏目：**新增 star / 已 star 跳过 / 待确认 / 未找到 / 截图清理**。
- 「截图清理」栏目按实际授权层级写：未获删除授权就写「未授权，未执行」；有授权但队列混入越权项就写「未执行，待审清单 N 项，去向 XXX」。
- 发现此前报告有误（star 状态、0⭐ 误记、归类错误）：下一轮主动修正并在报告里说明，不悄悄改口。

## 完成检查

- 每个处置都能对回授权层级：没有删除授权时，清理相关栏目写「未授权，未执行」。
- star 数与回读 204 一致；「待确认」项列全（含取不到指纹的同名仓库）。
- 删除类项要么有逐 uuid 的授权与回执，要么留在待审清单并写明去向；不出现「张数对得上就算一致」。
- 清单各轮记录完整；「未找到」项均已注明已试路线与用户侧取证位置（视频置顶评论、作者主页签名、简介链接）。
