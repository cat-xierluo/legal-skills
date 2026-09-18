# 书记员文件协议 v1

## 权威记录与目录

主 Agent 是唯一书记员。所有工具命令由书记员执行；角色仅得到本轮 packet 并交稿。记录工具不启动或唤醒 Agent，主 Agent 必须调用宿主子任务工具并等待结果。

```text
演练目录/
├── events/         # 书记员内部顺序事件，含私有材料，不能共享给角色
├── submissions/    # 各角色单独提交稿，主控指定唯一文件名
├── role-memory/    # 按角色分开、限制可见范围的备忘录
├── state.json      # render 生成的进度视图，可重建
└── transcript.md   # render 生成的公开发言笔录，可重建
```

每次运行使用独立目录。`events/*.json` 是唯一权威来源，包含初始化、材料版本、派发、正式发言、取消和关闭事件。它是书记员内部档案，不是所有角色可读的公用目录。对外只给筛选后的 packet 或笔录。

操作使用 OS 文件锁，同一时刻仅一个书记员命令占用写入权；稿件完整校验后写临时文件，再原子替换为新事件文件。事件编号连续，带前序 hash。hash 可发现事件内容变动和中间缺号，但没有外部可信末尾标记，无法仅凭链检测尾部事件被删除或整个目录回滚，不提供身份认证或对抗恶意篡改的保证。锁由 OS 在进程退出时释放；断电耐久性和网络文件系统不作保证，优先本地文件系统。

不要直接编辑 events、state.json 或 transcript.md 来改变事实；派生文件过期时重新 render。`.pending-*` 不是正式事件，读取记录时忽略，不自动提升为完成。

## 命令

从任意工作目录调用脚本绝对路径。下例假定 `clerk.py`、`materials.json` 与演练目录位于已指定路径，实际执行须替换示例路径。成功命令向 stdout 输出 JSON；业务校验失败退出码 2 并向 stderr 输出简明 JSON，命令参数错误则输出用法提示，同样不视为完成。

```bash
python3 /path/to/moot-court/scripts/clerk.py --run /path/to/hearing init --case-type civil --manifest /path/to/materials.json --max-turns 40
python3 /path/to/moot-court/scripts/clerk.py --run /path/to/hearing dispatch --role plaintiff --stage evidence --issue I-001 --prompt '说明交付主张的现有依据'
```

第二条返回完整 packet，主控保存到该角色独立工作位置或直接随子任务传入。packet 包含 `assignment`、筛选后的 `documents`、公开 `history` 与 `submission_template`。角色填好完整 submission_template，保存到主控指定的唯一提交路径；不额外添加字段。

```bash
python3 /path/to/moot-court/scripts/clerk.py --run /path/to/hearing commit --submission /path/to/hearing/submissions/plaintiff-T-0001.json
python3 /path/to/moot-court/scripts/clerk.py --run /path/to/hearing dispatch --role defendant --stage evidence --issue I-001 --prompt '回应上一发言的交付依据' --respond-to 3
```

`--respond-to` 接受一个或多个已入卷发言的整数 seq。示例 3 只适用于 init=1、dispatch=2、speech=3 的新运行；真实执行必须读取 commit 的 `accepted_seq`，不能猜编号。

阶段代码：`opening / evidence / questions / debate / closing`。脚本校验阶段枚举，不裁决各案法定程序顺序。法官主持顺序与主控回合预算仍须人工／Agent 审查。

## 发言合同

```json
{
  "schema_version": 1,
  "run_id": "从派发继承",
  "turn_id": "T-0001",
  "role": "plaintiff",
  "material_version": 1,
  "read_through": 1,
  "responds_to": [],
  "body": "本方观点、针对性回应、材料编号与定位、推理及待核实事项。",
  "citations": ["D-001"]
}
```

除 body 和 citations 外必须与当前派发完全相同。`read_through` 是派发前的最后事件编号，可能包含材料或调度事件，不等于最后发言编号。`responds_to` 是本轮必答发言编号，正文另可讨论其他可见历史。

脚本拒绝：未知字段、空正文、不同角色／运行／回合／版本／截止编号／必答集合、未知或未公开的引用编号。**正文有无真正回应、引用能否支持结论、私有内容是否被改写泄露，仍由主控与独立复核者检查。** 未通过语义检查时退回角色修稿，不由书记员代写。

同一回合同一内容再次 commit 返回原 `accepted_seq` 和 `duplicate: true`，不新增事件；已关闭运行也可重取这个同稿回执。同回合不同内容拒绝；更正必须另开回合引用原发言。回传自称“已提交”不构成入卷证据，以 commit 回执和正式事件为准。去重以仍完整保留的事件为前提：若已提交 speech 文件被删除，其完成信息也会丢失，不能保证再次提交被识别为重复。

## 状态、恢复与变更

```bash
python3 /path/to/moot-court/scripts/clerk.py --run /path/to/hearing status
python3 /path/to/moot-court/scripts/clerk.py --run /path/to/hearing packet
python3 /path/to/moot-court/scripts/clerk.py --run /path/to/hearing cancel --reason '角色执行超时，准备重派'
python3 /path/to/moot-court/scripts/clerk.py --run /path/to/hearing materials --manifest /path/to/materials-v2.json
python3 /path/to/moot-court/scripts/clerk.py --run /path/to/hearing render
```

有待交稿回合时拒绝新增派发或更新材料；先恢复原派发或取消，再按新材料重新派发。取消消耗原 turn_id，不复用身份；迟到稿不应被主控换成新回合字段后提交。新增材料使 material_version 递增，历史仍保留原版本。旧会话重建时，依靠角色材料包与本方备忘录恢复，不以猜测填补遗漏。

`status` 每次从事件重建，不读取 state.json 作为依据。`packet` 可重新取得当前任务，所以 dispatch 已成功但 stdout 丢失时不要重新 dispatch。commit 返回丢失时检查 status/事件或重试同稿。事件损坏或编号缺失时报错并保留现场，不能手工补 hash 或猜成功。

上述恢复针对事件仍保留的会话／进程中断。已知尾部丢失、恢复旧备份或回执与现存事件不一致时，不沿旧目录自动续跑；保留现场、核对原始回执与备份后另建运行并说明历史缺口，不能将合法前缀误当完整历史。

packet 的 documents 是当前版本，history 保留过去发言及其材料版本。旧版材料已变更或移除时，需回查的原文由书记员从对应版本快照中筛选当时已公开的材料后单独补入本轮任务，注明版本；角色不得自行读取 events。已经公开的发言无法通过后续将材料改为私有而撤回。

## 关闭与范围

```bash
python3 /path/to/moot-court/scripts/clerk.py --run /path/to/hearing close --reason '既定争点已演练，未解决事项已列入复盘'
python3 /path/to/moot-court/scripts/clerk.py --run /path/to/hearing render
```

关闭前必须没有待交稿回合。普通 close 至少要求三个必要角色均有正式发言；这只是最低协议条件，不能据此宣称流程充分。预算用尽、角色失败或材料不足时使用 `close --incomplete --reason '具体剩余事项'`，并生成部分笔录。已关闭运行只读／重渲染；后续演练新建运行并引用旧记录。

实现仅保存本地文本快照与发言，不自动检查原件存在、法源正确性、正文泄漏或角色是否真实由不同 Agent 执行。不可用这些命令的成功状态证明法律正确性、多轮稳定或跨 Runtime 已通过。
