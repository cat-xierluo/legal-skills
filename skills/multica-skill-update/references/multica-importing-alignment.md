# 与平台内置 `multica-skill-importing` 的分工

Multica 平台内置了一个 **`multica-skill-importing`** skill（`user-invocable: false`，随平台更新覆盖，**不可修改**）。本 skill 与它是**上下游关系，不是竞争关系**：

| | 内置 `multica-skill-importing` | 本 skill `multica-skill-update` |
|---|---|---|
| 职责 | 导入**单个**已知 URL/slug 的 skill | 按**清单批量**导入/刷新 |
| 输入 | 一个具体 URL 或 slug | `scripts/manifest.local.json`（N 条来源） |
| 触发 | 平台内部调用（不可被用户直接唤起） | 用户/Autopilot 主动调用 |
| 关注点 | 单次导入的正确性与结果解读 | 批量编排、幂等、报告、定时 |

## 协调原则

内置 skill 定义了「单条导入的权威语义」，本 skill **严格复用同一套语义**，不另立标准——它变我变，避免行为漂移。具体对齐了以下几点：

1. **唯一合法路径**：`POST /api/skills/import`（即 `multica skill import`）。绝不用 `npx skills add`（装到本地环境，Multica 无法管理），也绝不用 `multica skill update`（只改字段，不拉来源）。
2. **结构化结果信封**：不猜 exit code、不做字符串匹配，直接读 `status` 字段：

   ```json
   {"status": "created|updated|conflict|skipped|failed",
    "reason": "...", "skill": {...},
    "existing_skill": {"id": "...", "name": "...", "can_overwrite": true}}
   ```

   脚本 `_handle_result()` 逐一映射这五种 status，并在 `can_overwrite=false` 时把 `failed` 归类为「非本人创建」而非真实错误。旧版服务端只回 `409 + {error, existing_skill}` 或纯字符串时，回退到字符串判断。
3. **`overwrite` 的确切语义**：保留 skill ID、`created_by`、`created_at` **及 agent 绑定**，只替换 description/content/config/supporting files；且**仅原创建者可执行**。这正是"刷新同步"想要的语义，也是清单默认用 `overwrite` 的依据。
4. **服务端硬限制**（脚本在打包后预检并告警，不阻断）：

   | 限制 | 阈值 |
   |------|------|
   | 单文件 | 1 MiB |
   | 整包（解压后） | 8 MiB |
   | 文件数 | 256 |
   | 上传（压缩后） | 16 MiB |

5. **服务端会丢弃的内容**：dotfiles、`__MACOSX`、license 文件、二进制资产。本地打包时提前剔除，省流量也让预检数字贴近真实。
6. **`SKILL.md` 是保留文件名**：支持文件若也叫 `SKILL.md`（如 `references/SKILL.md`），导入**仍会成功但该文件被静默丢弃**。脚本会显式告警，避免"文件莫名消失"。
7. **zip 布局**：服务端 root 到**最浅的 `SKILL.md`**，顶层目录名仅作 name 兜底（frontmatter `name` 优先）。所以 `my-skill/SKILL.md` 嵌套布局与根级 `SKILL.md` 都被接受，本 skill 采用前者。
8. **agent 绑定用 `add` 不用 `set`**：`add` 追加，`set` 会**清空该 agent 所有现有绑定**再写入。本 skill 目前不动绑定关系；若将来扩展，只用 `add`。

## 为什么要排除工作产物 / 大体积媒体

**`archive/` 等工作产物目录**：实测 `legal-ocr` 的 `archive/` 达 7.6 GB / 11 万文件，整包打进去必然触发全部四项限制。剔除后仅 21 个文件 / 82 KB，导入成功。同类目录（`output/`、`tmp/`、`.cache/`、`node_modules/` 等）已一并加入排除名单，见 `scripts/sync_skills.py` 的 `PACK_EXCLUDE_DIRS`。

**大体积媒体资产自动剔除（体积兜底）**：目录黑名单永远补不全（如 `visual-card` 的 `assets/examples/` 有 154 张示例图 / 21.2 MiB，不在黑名单内，却同时超 8 MiB 与 256 文件双限制，导致该 skill 无法导入）。因此除目录黑名单外，脚本按两层规则剔除媒体资产：

1. **演示目录媒体**：路径落在 `examples`/`sample`/`samples`/`demo`/`demos` 下且后缀命中 `PACK_EXCLUDE_MEDIA_SUFFIXES`（图片/视频）的文件直接剔除——这些目录里的 **.md 等文档仍保留**（如 `legal-case-analysis/examples/*.md` 是运行时会读的范文，误删会破坏技能）。
2. **通用体积兜底**：任意目录下，体积超过 `PACK_MEDIA_MAX_SIZE`（256 KiB）且命中媒体后缀的文件也剔除。

两层都用"媒体后缀 + （目录或体积）"条件，只剃展示性大图，不误伤运行所需的非媒体大文件（模型权重、数据文件）与文档。剔除明细打印到日志（最多 8 条 + 余数），便于回查 `visual-card` 等技能为何体积骤降。
