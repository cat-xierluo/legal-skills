# Runtime 候选包准备器

`scripts/prepare_runtime_candidate.py` 只用标准库，从生产 Skill 目录显式抽取一份全新候选 bundle，供跨 Runtime 冷启动复测（G5）或独立验收使用。它是文件级准备工具，**不是盲测沙箱**：目录筛选只界定包内可见内容，不构成宿主工具权限隔离；是否通过 G5 仍由宿主实跑与独立验收决定，本工具不签 G5 或 `DOMAIN_VERIFIED`。

## 标准调用

```bash
python3 /path/to/moot-court/scripts/prepare_runtime_candidate.py \
  --skill-dir /path/to/moot-court \
  --manifest /path/to/case/materials.json \
  --task-file /path/to/runtime-task.txt \
  --output /path/to/new-bundle-dir
```

四个参数全部显式必需。默认不安装任何依赖、不联网、不启动宿主；源 Skill、案卷与任务文件一律只读，绝不修改。`--run-dir` 与 `--allow-unknown-placeholders` 为可选行为开关，语义见下。

## bundle 结构

| 路径 | 内容 |
|---|---|
| `skill/` | 显式允许集：`SKILL.md`、`LICENSE.txt`、运行必需 references（不含 `evaluation.md`、`blind-probe.md`）、书记员/预检/固定角色审计脚本、民事与刑事合成案卷样例 |
| `materials.json` | 调用方案卷的字节原样副本 |
| `task-source.txt` | 原始任务字节（保留占位符） |
| `task.md` | 占位符展开后的任务文本：`{skill_dir}` 指向 bundle 内 `skill/`、`{manifest}` 指向 bundle 内 `materials.json`，冷启动宿主不会读回源 Skill 或源案卷 |
| `manifest.json` | 全部摘要、允许/排除清单、投影记录与链接核验结果 |

运行目录不在 bundle 内预创建：`{run_dir}` 默认展开为 `<bundle>/hearing`（该目录不创建），或用 `--run-dir <绝对路径>` 指定路径（同样不创建）。书记员 `init` 接受不存在或完全为空的目录——提前创建好空的 `hearing/` 不会被拒，只要其中没有混入其他材料；工具不创建它是为了避免与包内输入混放。`--run-dir` 必须是尚不存在的绝对路径，且不得位于源 Skill 或 bundle（含 `skill/`）之内，否则拒绝；默认展开值 `<bundle>/hearing` 不受该限制。

## 占位符契约

任务文本必须至少各含一个 `{skill_dir}`、`{manifest}`、`{run_dir}`，允许重复出现；工具对三者做全量定点字符串替换（每次出现都展开），不 `eval`、不 `format`，不求值任何表达式。其他 `{token}` 默认 fail-closed 拒绝；确属任务文本本身（如字面 JSON 花括号）时加 `--allow-unknown-placeholders`，未知名将原样保留并记入 manifest 的 `unknown_placeholders_kept`。展开值与各占位符出现次数写入 `manifest.json` 的 `placeholder_expansion`，可复核。

## 允许集与排除

采用显式白名单而非递归全拷：`TASKS.md`、`CHANGELOG.md`、`DECISIONS.md`、`archive/`、各测试脚本、`prepare_probe.py`、`index_claude_trace.py`、`evaluation.md`、`blind-probe.md`、`semantic-probe-reviewer.json`、`claude-stream.example.jsonl` 及源中任何其他文件都不带入；`manifest.json` 的 `excluded_paths` 如实列出源目录中未带入的全部文件。引用依赖先核对再抽取，不因目录名盲删导致生产 Skill 断链。固定角色审计脚本随生产合同带入，其依赖的 WorkBuddy 冷启动审计公共解析器一并带入；两者仍只读归档，不启动代理。

## 投影（唯一允许点，fail-closed）

`SKILL.md`：源文末以"开发验证命令："开头的整段链接到评测与测试脚本。候选仅删除该段——要求标记唯一、位于独立段落起始；出现 0 次、多次、不在行首或段落边界歧义一律拒绝并交回 PM。投影前后 SHA-256 记入 `projections`；剔除后正文若仍出现任何排除项的文件名引用（含裸名），同样拒绝。

其余候选文件与源逐字节一致，`source_readonly.files` 记录读取时源 SHA，验收方可对源目录复算确认未被改动（本工具从不写源）。runtime-validation 等生产文档中的方法与历史摘要原样保留，不视为答案。

## 核验与拒绝

- 允许集逐项核实：存在、常规文件、自身非 symlink。源树内部的 symlink 目录不被遍历跟随，其下允许文件因缺席而被缺文件分支拒绝。
- 四个显式路径参数（`--skill-dir`、`--manifest`、`--task-file`、`--output`）本身与既有祖先组件均不允许 symlink；macOS 系统级软链（`/var`、`/tmp` → `/private/*`）豁免，再以 realpath 对账确保输出不落进源 Skill。`--output` 已存在一律拒绝。失败时清理只删除本次创建的文件与登记过的目录，不向未登记祖先爬升——预先存在的空输出父目录与调用方既有内容原样保留。
- 投影后候选 markdown 的相对 inline 链接与相对图片（`![...]`）逐条解析（去锚点），必须命中候选 `skill/` 目录内实际在包的文件；绝对路径目标拒绝；外部 URL 与 mailto 跳过、不联网。指向未带入内容、缺失文件或逃出目录即拒绝。
- 链接核验不宣称覆盖任意 Markdown：引用式链接（`[x][y]`、快捷式 `[x]`）、链接定义、脚注、转义方括号等可能藏匿未核验链接的形态一旦出现即 fail-closed 拒绝，并指明文件与形态。围栏代码块、HTML 注释与行内代码中的方括号/尖括号不视为链接语法，不误报。
- `manifest.json` 记录源/候选逐文件 SHA-256、原始任务/展开任务/案卷 SHA-256 与 `bundle_manifest_sha256`（对 manifest 核心字段的规范化 JSON 求 SHA，验收方删除该字段后同法复算）。
- 所有拒绝均输出中文错误并以退出码 2 结束，不抛 Traceback。

## 与 runtime-validation 的关系

G5 执行方拿到 bundle 后，把 `task.md` 作为统一任务文本、`materials.json` 作为只读案卷、`skill/` 作为唯一技能可见内容派发角色；角色 packet、提交稿与真实调用的对应仍由生产者按书记员协议自行保存，本工具不代写角色、不保存运行产物。
