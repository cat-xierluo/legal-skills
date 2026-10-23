# 重点项目画像与源码包

当用户点名一个仓库，或每日候选需要比 README/Release 更完整的判断时使用。目标不是给仓库打分，而是收集足够事实回答四个问题：它采用什么方法、如何生产、对哪些本地 Skill 有价值、能否直接用于生产。

## 轻量画像

```bash
python scripts/repository_profile.py profile owner/name \
  --data-dir ~/.local/state/github-star-manager/discovery \
  --skills-root ~/.codex/skills
```

画像只做 GitHub GET：仓库元数据、递归树、README、最新 Release、最多 4 个 `SKILL.md` 和最多 5 个依赖声明。它输出 Skill 单元、运行时代码/媒体/资产比例、能力线索、许可证风险、本地 Skill 概念匹配、本地已有快照和源码包建议。树截断、读取失败、超过取样上限都会显式保留；API 失败不覆盖上一次完整画像。与每日链使用相同 Release 格式；`evidence_revision_complete=false` 的部分画像不能当作完整证据修订。

能力标签来自 README、描述、topics、依赖与 Skill 描述，目录名不单独当作能力证据。画像不包含任何仓库专属的预设结论；四类候选结论必须由 Agent 在读完上游契约和本地等价物后给出。本地匹配按既有领域概念过滤，只用于决定优先阅读顺序，不是适用性结论。画像会给出四类候选结论：上游能力包、生产后端/风格库、只吸收部分方法、不适用或有风险；真正落结论前必须核本地 Skill 的输出契约、上游样例、资产许可和依赖体量。

## 焦点仓库

```bash
python scripts/repository_profile.py focus add owner/name --reason "..." --data-dir ...
python scripts/repository_profile.py focus list --data-dir ...
python scripts/repository_profile.py focus remove owner/name --data-dir ...
```

focus 是少量重点仓库的人工清单，不是目标 Skill 登记表，也不会替代动态扫描。添加原因只说明为什么值得反复看。

登记后该仓库在每日 `focus_deltas` 中保留检查汇总，即使没有组件匹配；取证仍按总预算和轮巡分配，未轮到明确显示。focus 只影响优先级，普通收藏同样自动轮巡。具体机会始终绑定组件而非 `"*"`；组件声明的排除条款与该上游实际相关能力冲突时才标 `conflicts_with_stated_scope`，用于阅读预警。字段与覆盖边界见[每日流程](daily-opportunities.md)。

## 本地已有快照

画像会扫描已装套件的 `reference-library/sources/<owner>--<repo>/`，优先读相邻 `manifests/` 的仓库身份和固定 commit，辅以 Git/README 目录表。命中时把 `source_package.recommended_strategy` 改为 `existing-local-snapshot`，并给出快照路径、固定 commit 与上游 head 的比较。参照库由所属组件管理逐文件哈希、省略清单和研究结论，GSM 不用通用 `source-package update` 操作它，也不因版本落后反复推荐。`recommended_paths` 在已有快照时为空。

## 显式源码包

默认不克隆。画像建议需要源码且本地没有快照时，才创建固定 commit 的有界包：

```bash
python scripts/repository_profile.py source-package create owner/name \
  --data-dir ... --target ~/.local/state/github-star-manager/source-packages/name \
  --path core --path plugin/skills/name --path package.json \
  --max-bytes 268435456
python scripts/repository_profile.py source-package status owner/name --data-dir ...
python scripts/repository_profile.py source-package update owner/name --data-dir ...
```

- create 先按 Git tree 计算一个保守上界（所选路径及仓库根文件），超预算直接拒绝；然后执行 depth-1、blob-filtered、non-cone sparse clone，并固定远端 HEAD。该估算可能高于实际检出大小，不会低估落盘预算。路径必须真实存在于树中；文件和目录路径都可使用；clone、稀疏设置或检出任一步失败都会移除目标目录（含用户预先创建的空目录），保证可重试。
- `--target` 只有 create 需要；status/update 从 manifest 读取目标目录。
- 默认预算 256MB，可用 `--max-bytes` 收紧。样式库、示例片、字体、模型等大媒体应留在上游，只取接口、核心实现、许可证/credits 和必要构建脚本。
- status 只读报告本地 commit、dirty、远端 HEAD 和是否有更新；update 只允许干净且匹配 manifest 的包，更新后保留 previous_commit。
- 源码包仅用于阅读、diff、许可与安全审查。本命令不安装依赖、不执行 setup、不自动复制代码或资产进 legal-skills，也不把上游提示当作执行指令。
- 若要作为生产后端，另行走目标 Skill 的实验与机会卡：一个有界样例、真实产物、验收日志，未执行前只能记录 `researched` 或 `experiment_proposed`。
