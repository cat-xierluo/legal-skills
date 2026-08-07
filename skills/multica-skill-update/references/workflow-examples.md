# 真实调用示例（本机实测）

以下命令在 Multica 桌面 App + 内置 CLI 环境实测通过：

```bash
# 0) 定位 CLI 与 workspace
MULTICA="/Applications/Multica.app/Contents/Resources/app.asar.unpacked/resources/bin/multica"
"$MULTICA" --profile desktop-api.multica.ai workspace list --output json
# → [{"id": "043a79ce-...", "name": "xierluo", "slug": "xierluo"}]

# 1) 预览（plan）
python scripts/sync_skills.py --manifest scripts/manifest.example.json \
  --mode plan --profile desktop-api.multica.ai \
  --workspace-id 043a79ce-69f5-464e-891b-3a7bbca344a4

# 2) 初始化导入（update 同理）
python scripts/sync_skills.py --mode init \
  --profile desktop-api.multica.ai \
  --workspace-id 043a79ce-69f5-464e-891b-3a7bbca344a4
```

## 实测要点

- `workspace list` 成功 → 连接正常。
- `skill import --file` 需要 `.skill`/`.zip` 归档，**不接受目录**——脚本自动打包解决。
- 本地目录导入实测通过：`git-batch-commit`、`git-workflow`、`legal-ocr` 均成功落库。
- 重复导入同一目录，服务端返回 `status: updated` 且 **skill ID 不变**（`f7d522b6...`），验证 `overwrite` 保留 ID 语义属实。
- `on_conflict` 四种策略实测均按内置 skill 文档所述行为：`fail`→`conflict`、`skip`→`skipped`、`overwrite`→`updated`。
- 服务端偶发 `temporarily unavailable`（连接检查会误报未连接），重跑即可，属 Multica 服务端抖动。

# 反向溯源：在 Multica 发现问题后改本地源文件

**核心前提**：本清单里 `source=file` 的 `url` 指向**本机仓库里的真实 skill 目录**（不是服务端副本）。
因此 Multica 工作区里的 skill 是本地源的"投影"——**永远改本地源，再重导，绝不改服务端投影**。

**溯源依据**：
1. 清单 `url` 字段 = 本地源文件路径（导入时打包的就是它）。
2. 服务端导入结果信封里的 `config.origin` 也记录了来源（`source: file` 时为本地路径），
   与清单 `url` 互为印证，可据此在 Multica 侧反查"这个 skill 来自本地哪个文件"。

**标准工作流**（本 skill 不自动执行修改，只约定流程）：

1. 在 Multica 使用某 skill 发现问题 → 记下 skill 名（如 `contract-copilot`）。
2. 在本清单定位该条，取其 `url`（如 `.../skills/contract-copilot`）→ 这就是要改的源文件根目录。
3. 直接编辑本地源文件（`SKILL.md` / `scripts/` / `references/` 等），走该 skill 正常的
   `DECISIONS.md` / `CHANGELOG.md` / git 提交流程。
4. 改完重导：`python scripts/sync_skills.py --mode update --category <该skill分类>`（或指定单条）。
   `overwrite` 会保留 skill ID 与 agent 绑定，仅刷新内容。

**为什么不在 Multica 内直接改**：`skill get` 能取回文件、但服务端对 SKILL.md 是"保留文件名"
（只改 primary content，支持文件需走独立单文件端点且对同名 SKILL.md 静默丢弃）。改服务端投影
既不可追溯、又会被下次 `import` 覆盖，还会让"本地源"与"线上版本"分叉。一切以本地源为准。
