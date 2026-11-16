# 截图来源：从照片库批量找项目、Star 与清理源图

> 适用：用户说「看看我最近的截图里有哪些可以 star 的」「从截图里找项目并 star」，且来源是 **Mac 照片库**（iPhone 截图经 iCloud 同步）而非单张附图。
>
> 分工：mac-photos 技能负责图库读取、OCR 索引、搜索与标记删除；本流程只负责把「截图 → 仓库 → star → 清理」编排成可交付结果。

## 0. 范围对齐与自检

1. **先量范围**：`photos_read.py stats` 看索引规模与最新日期；用户没给范围时默认「近 30 天」，并把范围的确定结果写进报告。
2. **自检**：`photos_read.py doctor` 五项全绿再开始（完全磁盘访问、osxphotos、OCR、索引）。
3. 索引最新日期落后于今天时，先增量 `scan` 再处理；未入索引的新图用 `osxphotos export --uuid <uuid> --preview-if-missing` 导出预览版补读 OCR（避免触发 iCloud 下载权限）。
4. 未命中不要直接说「没有」：说明已查范围（日期窗口、索引张数、排除规则）再下结论。

## 1. 摄取与线索提取

- 列出范围记录（date / uuid / status / text / links / github / github_guess），先看机器提取的完整 `github.com/owner/repo`——最可靠。
- 短链接候选（`github_guess`）必须语义复核后再采信；截图 OCR 的 owner/repo 先怀疑误读，按 [`owner-repo-disambiguation.md`](owner-repo-disambiguation.md) 处理。
- 无链接但功能描述清晰（「我手搓的动效 Skill」「批量剪辑模板」）时，按功能 + 技术指纹搜索，不要放弃。
- 实拍照片（带相机 EXIF）不属于信息图集，排除；Live Photo 视频部分无文字价值，跳过。

## 2. 仓库核实与分级

逐个候选仓库：

- 存在性 + 元数据：`gh api repos/<owner>/<repo>`（description / stars / fork / archived / pushed_at / license）。
- **排除干扰**：同名搬运版、社区 fork、学术同名项目；排除要留理由（语言、star 量级、发布日期、目录结构）。
- **内容指纹**：候选的 README/SKILL.md 关键句（触发词、工作流、依赖）须与截图语境吻合；名字相同但指纹不符 = 不是同一个，不 star。实测：同名 `motion-design-prompt-generator` 仓库 SKILL.md 无截图展示的 Priority order/motion.ts 指纹，判为不同项目。
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

## 4. 清理源图（用户通常 star 后即要求删除，避免二次翻看）

```bash
python3 scripts/photos_read.py mark --uuid <U1> <U2> ... --delete   # 标记
python3 scripts/photos_read.py prune                                  # 干跑预览
python3 scripts/photos_read.py prune --execute --yes                  # 真删（需用户屏幕点一次系统允许）
```

- **uuid 永远从索引按内容取**：脚本里 `load_index()` 后按文本/日期匹配置信 uuid，绝不手抄——抄错一位会删错或删不到（实测两次翻车）。
- 真删会弹一次系统确认框，提前提醒用户点「允许」；**干跑张数必须与确认框张数一致**，不符先取消再拆批。
- prune 前检查待删队列里是否混入用户自己标记的项：如实披露合并计数，拿到同意再执行。
- **索引与图库会失同步**：删除失败先 `osxphotos query --uuid <u>` 核实资产是否已不在（用户常在手机/相册手动删）；确认不在后把悬挂的 `to_delete` 同步为 `deleted`（显示为「已删·档案」），文字档案保留，仍可按内容搜索。
- 用户可能同时在相册页面自行删除：若索引已是 `deleted`，不再重复操作，报告里说明。

## 5. 清单文件与报告

- 清单落 `$CLAWD_REPORTS`（`folder_rules.py suggest` 解析），按轮次追加：日期-来源截图-处置-理由；追加后检查**没有顶掉已有标题或打乱段落顺序**（实测踩过）。
- 每轮报告固定栏目：**新增 star / 已 star 跳过 / 待确认 / 未找到 / 截图清理**。
- 发现此前报告有误（star 状态、0⭐ 误记、归类错误）：下一轮主动修正并在报告里说明，不悄悄改口。

## 完成检查

- star 数与回读 204 一致；待删队列清零或已说明去向；清单各轮记录完整；「未找到」项均已注明已试路线与用户侧取证位置（视频置顶评论、作者主页签名、简介链接）。
