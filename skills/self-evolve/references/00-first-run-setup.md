# 初始化与第一次使用

本公开路线只需 Python 3.11+，不需要单独的模型 API Key，也不要求先配置 YAML 或定时任务。

## 1. 运行初始化扫描

让当前 Agent 在本 Skill 目录运行：

```bash
python3 scripts/first_run.py
# 同等入口
python3 scripts/public_workflow.py scan
```

默认先处理最多 200 个新建/变化输入。首次自动建立专用外置数据目录和 SQLite 账本；运行结果给出证据包 `packet` 与初筛 HTML `report`。再次运行复用账本，不重新解析未变会话；预算未处理的旧会话继续补齐。不能因看到报告就认为深度分析已完成。

## 2. 让当前 Agent 分析并生成最终 HTML

读取 `packet`，按 [分析合同](18-public-workflow.md) 判断经验、改进及 Skill 沉淀去向，写 analysis JSON 后运行：

```bash
python3 scripts/public_workflow.py import-analysis \
  --packet <本轮packet.json> --analysis <analysis.json>
python3 scripts/public_workflow.py status
```

打开返回的总览 HTML，通过侧栏进入个人画像、深度分析、Skill 沉淀、会话与证据、扫描与覆盖和运行说明。确认实际覆盖的 Runtime、来源完整性、失败和预算待处理、分析证据及 Skill 安装说明。移动报告时一并保留同前缀的七个 HTML 文件；它们可以直接离线打开，不需要启动服务。“建议创建”尚不是一个已完成、可安装的 Skill。

## 3. 数据保留在哪里

默认沿用本机平台数据根，包含 `runtime/public-workflow/ledger.sqlite` 和 `runs/<run-id>/` 的证据包、报告与分析修订。只保存脱敏摘要和处理记录，不复制原始会话。保留这个目录即可保留初始化节点、去重记录、失败与全部历史扫描。

需要自定义时，**首次运行前**设置一个专用空/不存在的叶目录：

```bash
export SELF_EVOLVE_DATA_ROOT="<专用数据目录>"
```

也可复制 `config/data_root.example.yaml` 到 `config/data_root.yaml` 后配置 `data_root`（需可选 PyYAML 才读取 YAML）。不要将主目录、共享非空目录或 Skill 源码目录当作状态根。移动状态前保留整个旧根，按旧工作台迁移合同核对；不要只搬 HTML 然后清空账本。

`data_root.yaml`、`core_skills.yaml`、`asset_owners.yaml` 是本地覆盖文件，不入 Git，也不进入发行包；发行清单的 `excluded` 字段会登记这三个路径。若旧安装中已有同名文件，升级后保留本地版本继续使用。

## 4. 自定义来源与排障

默认扫描已登记 Runtime 的标准目录；自定义配置根或布局可显式补充：

```bash
python3 scripts/public_workflow.py scan \
  --source <runtime>:claude=<JSONL会话目录>
```

支持的格式为 claude / codex / trace / gemini。格式不匹配会明确失败，不把存在的目录当成功。ZCode 默认是只读任务搜索索引摘录；完整消息的新版本 adapter 后续再接。详细目录、覆盖局限和格式合同见公开版工作流。

退出码：0 表示本轮扫描或导入执行完成；1 表示扫描存在部分读取/解析失败（报告和成功记录仍保留）；2 表示参数、账本或导入校验失败。失败记录在后续预算允许时重试，数据库损坏时保留原件，不自动重建。

## 5. 建议每周调用

确认首次 HTML 与覆盖后，在正在使用的 Runtime 中配置每周一次的定时 Agent 调用，复用 [每周提示词](18-public-workflow.md)。时间与时区由用户决定，界面没有定时能力时保留手动入口。只运行系统 cron 的扫描脚本不能代替 Agent 分析。配置任务、调用成功和真实周期触发分别核验。

旧首次引导不再自动运行 SiliconFlow/Claude CLI 分析；历史部署仍可按需查 [历史工作台](19-legacy-workbench.md)。

## 本地配置与旧调度

`config/data_root.yaml`、`config/core_skills.yaml`、`config/asset_owners.yaml` 和 `config/scheduled_tasks.yaml` 是本机配置，不纳入 Git 或发行包。公开主流程不要求这些配置；仅在需要相应功能时复制同名 `.example.yaml` 并按本机情况填写。旧调度属于兼容入口：未配置时不运行任务；模板任务默认关闭，须由用户逐项启用并自行配置外部 Cron。

发行构建以指定 Git 提交中的 `release-files` 允许清单为范围，支持仓库根下 `self-evolve` 与 `skills/self-evolve` 布局；维护文件和本机配置另受硬排除保护。独立发行目录不自带源仓历史，重建发行物需要提供对应 Git 仓库及提交 OID。
