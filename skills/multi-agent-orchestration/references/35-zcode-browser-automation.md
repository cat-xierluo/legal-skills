# ZCode GUI 浏览器自动化：操作映射、无头与监督边界

本页承接[GUI操作合同](34-zcode-desktop-remote.md)。浏览器驱动见[scripts/zcode-browser-driver.cjs](../scripts/zcode-browser-driver.cjs)，Orca专用监督适配器仍未实现。驱动由真实ZCode GUI worker实现，PM沿原会话审查返修；验证范围见第5节和TASKS中的`ZCODE-GUI-DRIVER`卡。

## 1. 分开浏览器驱动和任务监督

先建立 `PM → 浏览器驱动 → localhost ZCode Web → 本地内核` 的路径。GUI功能和权益依据沿用GUI合同，不因headless或使用脚本而改走独立CLI模型通道。

Orca监督的对象可以是控制GUI的worker，但须有真实的启动、身份、收件、终态、资源释放合同；GUI页面本身不能冒充Orca worker。2026-10-02本机版本指南与`worker-start --help`显示：

- `worker-start --agent`启动已支持的Agent；没有经此次核查证明可直接注册任意Playwright程序的通用backend接口。
- `terminal create`后`dispatch --inject`能建立Task/Dispatch上下文，却明确保持`unsupervised`，没有supervised资源行；不能据此声称Orca已管理浏览器进程。
- 短期可设计为已支持的受监督Agent调用浏览器驱动，沿其真实Dispatch回报；这会多一层Agent成本，且浏览器/服务子进程仍须验证归属与清理。本组合尚未实测。
- 专用程序适配器需另补Orca正式扩展/准入与生命周期集成，不能假扮`--agent zcode`、复制旧capability或覆盖现有CLI启动桥。Orca终端活着不证明ZCode任务活着。

因此浏览器自动化可以先独立使用，不把Orca适配作为前置。正式接入前分别验证任务投递、等待/审批、回报、断线不重投及资源收口。

## 2. 记录页面合同，不回放整页快照

保存运行版本、页面用途、稳定定位器、前置条件和动作后置条件。完整HTML或临时snapshot ref可用于诊断，不作为跨运行定位依据；不要固定`@31`这类临时编号或屏幕坐标。

2026-10-02 runtime3.14.3真实页面映射：

| 操作/区域 | 首选Playwright定位 | 必要后置条件 |
|---|---|---|
| 选择项目入口 | `getByTestId('composer-workspace-trigger')` | 打开后现场核选项；选中后的workspace绝对路径符合任务卡 |
| 输入区 | `getByRole('textbox')` | 唯一、可编辑；原草稿为空或属于本任务，填入后精确回读 |
| 模式入口 | `getByTestId('chat-mode-select-trigger')` | 实际模式与合同一致，不把打开菜单当配置完成 |
| 添加上下文 | `getByTestId('chat-attachment-button')` | 授权的材料已挂到正确任务，未混入无关材料 |
| 发送 | `getByTestId('v4-composer-send')` | 唯一提交后核同session/input；空框或按钮状态不单独证明接收 |
| 自动化入口 | `getByTestId('automations-open')` | 只证明入口存在；创建自动化须另有具体任务授权 |
| 插件入口 | `getByTestId('plugin-store-sidebar-open')` | 不因打开入口取得安装授权 |
| 设置入口 | `getByTestId('task-settings-button')` | 不为方便派发修改全局配置 |

这些test ID在该版本已观察，不保证以后不变。新任务、模型选择、会话定位与工具状态仍须按当前页面取得定位证据后补映射。优先test ID或role/name；匹配为零、多个或后置条件失败时，返回页面变化错误，刷新最小DOM重新识别，不能静默改点另一个按钮。

### 2.1 跨机器页面映射的适用范围

2026-10-02官方远控3.14.4在另一台Mac上的实测，以下test ID均唯一：`v4-composer-input`、`v4-composer-send`、`chat-mode-select-trigger`、`chat-model-select-trigger`、`task-new-button`。这支持复用定位与动作合同；连接鉴权、事件送达、状态来源和启动入口仍须各自验证。

| 层 | 复用与边界 |
|---|---|
| 页面动作 | 可复用已观察的test ID，仍须每次核唯一定位与后置条件 |
| 连接 | 官方配对链接与loopback地址分别处理；当前脚本只接受loopback，不直接支持官方远控URL |
| 执行环境 | Skill版本、runtime路径及预算在目标机核验，不由PM机器或同步目录名推断 |
| 状态读取 | 跨机须从目标宿主核本任务原生记录；当前脚本的本地SQLite读取不是远端监控接口 |
| 发送确认 | 草稿精确回读及一次点击仍不等于接收；无真实input/session时保留未确认并对账，不自动重投 |

首次尝试未接收的记录保留；用户要求继续后，PM核旧输入不存在，缩小为单会话串行轻量任务，经官方远控完成两轮、共3次只读工具，原生input promoted及turn completed已核，刷新重连仍保留交付。实际provider为`account:bigmodel-start-plan`、GLM-5.3-Flash、yolo；真实cwd为默认workspace，按绝对路径读取Legal Skills。任务与证据见TASKS的`ZCODE-REMOTE-HOST-VALIDATION`卡。

本轮有效步骤：等工作区与模型加载完成，明确选择目标provider；用原生粘贴填写富文本输入，回读完整草稿，并在下一次观察确认仍保留后再单次点击；随后从目标机原生输入核接收。一次紧接粘贴的续聊点击同样未接收，PM先对账后再沿原会话恢复。此步骤是实测操作建议，未做单变量实验，不能断言此前失败必由fill、粘贴时序或模型引起；跨次回读不能替代发送后的原生回执。

远端MAO2.34.1仍缺新驱动；本机配方的zcode.mjs入口缺失，研究找到官方包内glm/zcode.cjs候选并由PM核存在/hash，尚未验证其Web参数。目标机localhost、脚本headless跨机自动派发及Orca监督仍未验收。本次用户继续指令下的具名单任务资源例外由任务卡记录，未改变默认预算策略，不能推广为自动绕过。

## 3. 可调用驱动与状态合同

先按[本地Web启动配方](34-zcode-desktop-remote.md)启动专属服务，并确认工作区、资源预算与任务授权。驱动默认无头；`--headed`仅用于可见调试。依赖Node.js、已安装的Playwright与Chromium；只读SQLite优先使用`node:sqlite`，缺失时使用系统`sqlite3`。缺依赖时退出并提示，不自行安装。

以下从Skill目录执行，路径示例须替换为本机绝对路径。服务地址只接受不带账号、query和hash的loopback基础URL；本版不支持带token的远控网址。

```bash
node scripts/zcode-browser-driver.cjs inspect --url http://127.0.0.1:18490 --workspace /absolute/workspace
node scripts/zcode-browser-driver.cjs submit --url http://127.0.0.1:18490 --workspace /absolute/workspace --task-id TASK_ID --prompt-file /private/tmp/task.txt --state /private/tmp/task-state.json
node scripts/zcode-browser-driver.cjs observe --state /private/tmp/task-state.json
node scripts/zcode-browser-driver.cjs collect --state /private/tmp/task-state.json
node scripts/zcode-browser-driver.cjs follow-up --state /private/tmp/task-state.json --input-id REVIEW_R1 --prompt-file /private/tmp/review.txt
node scripts/zcode-browser-driver.cjs observe --state /private/tmp/task-state.json --input-id REVIEW_R1
```

| 命令 | 合同 |
|---|---|
| `inspect` | 读页面及server-info，观察定位器、workspace、模式、模型；不发送任务 |
| `submit` | 新任务草稿回读、发送前持久intent、同state唯一点击；绑定真实session/input，未确认保留unknown |
| `observe` / `collect` | 只读原生SQLite，核marker、session、input、promoted message与turn；最终文本不包含reasoning/tool |
| `follow-up` | 按精确session ID恢复，并核原输入marker；每轮input-id单独去重，恢复无法证明时返回UNSUPPORTED，交PM沿原会话处理 |

stdout为JSON；退出0表示调用/对账成功，**不等于任务完成或PM验收通过**；退出1表示拒绝/错误，2表示unknown，3表示不支持恢复。原生DB尚无turn终态时保持未确认，不能由input promoted或一段助手文本推断完成；错误/取消仍需PM处理。`collect`是有界状态与文本读取，不自动验收文件产物。

状态文件、prompt、锁和私有日志保存在本机非Git目录。同一任务必须复用原state；修改URL、workspace、task-id或prompt会拒绝。同state锁竞争须拒绝；残留锁由PM先核原进程及副作用后处理，不自动抢锁。记录intent之后，无论断线、超时或进程崩溃，都只能对账，不能通过删除state或换state重发。该策略优先避免重复执行，**不保证分布式exactly-once或必达**。

独立浏览器context不保证继承当前桌面/另一页的模型选择。每次核页面实际模型、模式与原生provider记录；不能仅凭GUI路径推断本轮使用了哪个账号通道。需要特定模式而自动驱动尚不能核实时，沿原GUI由PM明确选择，不修改全局默认凑条件。

每次命令关闭自己创建的浏览器，保留服务及任务；服务由启动者按精确owner清理。没有单独`prepare`/`close`命令，没有定时监督守护进程，也未接入`spawn-worker.sh`。复杂审批、其他业务会话接管、跨机器运行与长期稳定性不在本版已验范围。

## 4. Headless 与可见调试

Playwright支持`chromium.launch({ headless: true })`；用相同动作合同切换有头调试或人工接管。当前localhost页面的认证来自本地服务，本次全新临时浏览器上下文可直接访问，不需要复制用户浏览器凭证。若部署启用token或登录，沿既有授权处理，不把明文会话资料放入Skill。

Headless只隐藏浏览器窗口：本地Web服务、内核及工具仍在运行并占用资源。需要交互处理时暂停该任务输入并转可见界面，原session身份继续保留。需要屏幕、系统弹窗或特定浏览器能力的具体操作另做代表性验证，不由首页探针推断所有动作均已覆盖。

依赖：Node.js（测试需要可用的`node:sqlite`）、已安装的Playwright及匹配Chromium。本机已具备Playwright1.61.1与Chromium149.0.7827.55，本次未安装。依赖缺失时明确缺项，按环境管理规则安装，不自动执行全局安装或覆盖用户浏览器。

若尚未具备依赖，先按env-doctor规则确认隔离安装位置；以下仅为安装配方，不由驱动自动执行：

```bash
npm install --prefix /absolute/driver-deps playwright@1.61.1
/absolute/driver-deps/node_modules/.bin/playwright install chromium
NODE_PATH=/absolute/driver-deps/node_modules node scripts/zcode-browser-driver.cjs inspect --url http://127.0.0.1:18490
```

## 5. 验证与来源

2026-10-02当前候选验证：

- 远端Start Plan/GLM-5.3-Flash原审查会话接续两轮真实返修：R1调用实际submit/follow-up与FakePage/SQLite，证实两次读取可记录SHA(A)而发送B，撤回原报告整体fail-closed判断；R2仅从同一原始Buffer生成hash/text，PM独立审查并核30/30项测试与工具退出码。两项新增修复回归放回冻结旧驱动均失败，证明能检出旧问题；字节SHA与解码行为保留。验证过的两个候选以SHA核一致后接入本机，细节及证据索引见TASKS的`ZCODE-GUI-PROMPT-READ-CONSISTENCY`卡。此为PM浏览器操作的真实多轮交付，不扩大为脚本自动派发/续聊验收。

- 真实GUI实施worker在原会话完成代码交付、三轮PM纠偏/返修，GLM-5.3/max/yolo，原生provider为个人Coding Plan。首次探索回合由PM取消，保留失败记录；后续3轮completed。该证据证明PM经GUI派工/审查可用，不冒充新脚本端到端成功。
- 26项定向测试通过：重复调用不再点击、发送不确定不重投、真实子进程锁竞争、缺失/损坏/同PID锁、身份/目录冲突、最终文本门控、模型未就绪、恢复失败拒绝等。PM另修复真实项目标签误判及助手error判定。
- 真实headless inspect已就绪；Legal Skills目录的实际草稿填入/回读/配置检查/intent已走到发送前，由PM拦截发送，实际点击0次。另进程重复submit返回unknown，未打开浏览器或重新发送。
- `collect`从实施worker的精确R3 input读取原生completed turn及1353字符最终文本，排除reasoning/tool。此state由PM依据已知原始身份导入，仅用于读取验证，不能当作脚本submit回执。
- default工作区原会话在新context侧栏不可定位，follow-up实际返回UNSUPPORTED，零发送；其发送/去重路径只有fixture验证。保留原会话由PM接管，不另起任务替代。

**仍未验收**：新驱动的真实新模型派发→完成→跨进程续聊全流程。验收阶段内存探针因swap比率达到阈值返回exit3/slots0，按MAO预算规则暂缓新模型任务；恢复后沿TASKS原卡继续。复杂工具/审批、长期监控、多轮指令稳定性、指定模型/最高权限自动选择及Orca监督组合均为`NOT_VERIFIED`。该边界不因发布链已实测而改变：PM实际浏览器派发→回合监控→独审→远端GUI作者自己safe-push/唯一draft PR的发布链见 [38-zcode-gui-remote-pr.md](38-zcode-gui-remote-pr.md)（PR257/PR258具名已验），与本页脚本自动新派发、长时全自动稳定互不推导。当前驱动只观测配置，PM须另行满足任务的权限与模型合同。

安全扫描与基线均309项、high2无新增，既有告警不冒称全Skill安全PASS；Harness/指令稳定性形式门禁未通过。当前代码、测试日志、页面探针、原生回合、指纹与资源清理由TASKS的`ZCODE-GUI-DRIVER`卡索引。历史无头零发送探针由`ZCODE-BROWSER-AUTOMATION`卡索引。

官方文档：[Playwright定位器](https://playwright.dev/docs/locators)、[浏览器与headless](https://playwright.dev/docs/browsers)。Orca接口以本机`orca skills get orchestration`及其`references/low-level-topology.md`、`orca orchestration worker-start --help`为准，使用前读取当前版本。
