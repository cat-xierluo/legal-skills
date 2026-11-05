# 本机手机号与身份核验

## API直连优先

默认直接运行 `download_zxfw.py --url "{短信完整链接}" --output "{私密暂存目录}"`，不要在运行前读取 `lawyers.json`、列出律师配置或询问手机号。已从上下文确定的律师ID可以传入，但成功的直连路径不读取配置。

- 正常首次运行先只读请求文书列表。成功则直接下载；不查询 `getSfhyKg`、不提交 `checkSdryxx`，`identity.status=not_requested`、`direct_api.status=accessible`。即使网页开关为true，也不据此索取手机号。
- 只有列表API明确要求身份核验，才进入下方配置与问答流程。识别依据是明确核验/后四位提示，不能仅凭401/403、普通业务错误、空列表、文件损坏、网络超时或网页开关推断。
- 默认不发送签收。已有授权时，先完成只读匿名探测；可读或核验成功后，发送一次签收并重新取正式列表下载。签收回执未知不重发，仍尝试下载。
- 失败清单续跑先核验用户的新答案，不重复匿名探测；清单会保留原签收状态。即使核验要求出现在签收后的刷新列表，后续恢复也不会重发已发送的签收。
- `--identity-only` 是用户明确要求只核验时的专用模式，仍不取列表、不下载、不签收，不作为默认下载的前置探测。

## 确需核验后选择凭据

核验要与法院为这条链接登记的手机号或证件匹配。**短信称呼可能是当事人，而登记的接收手机号属于代理律师**；不能仅凭短信称呼断言律师号码一定无效。2026-11-04 的真实实例已出现当事人称呼与本机律师手机号核验通过的组合。

- 本人办理、已确认由当前律师接收，或用户指定用本机号码时：复用已匹配的律师配置。
- API已明确要求核验，且用户明确这是客户转发、登记客户手机号的短信、后四位未知时：询问该短信实际接收手机号的后四位，不先试律师号码。
- 已选本机号码被拒绝时：立即返回用户问题，取得实际登记手机号后四位后重试；不以一次拒绝判断链接失效或登记一定属于谁。
- 多位律师的配置不能遍历。`lawyer_id` 按人稳定复用；Agent 已从上下文匹配身份时直接代入，不重复让用户选择。

## 本机配置：首次询问，以后复用

真实配置为本 Skill 目录内 `config/lawyers.json`，公开模板为 `config/lawyers.example.json`。列表API已明确要求核验时才读取配置、匹配当前律师；缺少本次所需资料时才询问：

> 请提供这位律师的姓名和手机号，供法院短信核验使用；号码会仅保存到本机私有配置，以后直接复用。

收到回答后用配置脚本保存，再接续原下载任务。已有配置不重复询问；用户更正号码时只更新对应律师。无需提前收集整家律所的资料。

```bash
# 交互录入本机律师手机号，输入不回显
python3 scripts/lawyer_config.py set --lawyer-id lawyer-a --name "律师姓名"

# Agent 已取得资料时通过 stdin 传 JSON，不把号码放进命令参数
python3 scripts/lawyer_config.py set --lawyer-id lawyer-a --name "律师姓名" --stdin

# 只显示身份与字段是否具备，不输出手机号或后四位
python3 scripts/lawyer_config.py list
```

`set --stdin` 接收 `{"mobile":"用户提供的手机号"}`；按需支持 `id_last4`。只收集证件后四位，不收集完整身份证号。程序调用使用 `subprocess.run([...], input=json.dumps(...), text=True)`，不打印输入内容。

配置脚本使用独占写锁、原子替换和 `0600` 权限。本 Skill 的 `.gitignore` 排除真实配置、锁和临时配置；公开包只带 example，升级不覆盖实际配置。`.gitignore` 只防 Git 误收录，分享或打包 Skill 时也须排除真实配置与 `archive/`。

现有 `delivery_recipient` 仅是归属提示，**不是跨案件的事实证明**。显式 `--lawyer-id` 优先；只在用户已确认当前归属且恰有一位标记时才可省略 ID。多个或无标记时返回 `lawyer_selection_required`，不提交任何后四位核验。

`status=needs_config` 的接续方式：

| 原因 | 操作 |
|---|---|
| `lawyer_selection_required` / `unknown_lawyer_id` | 此时才列出本机身份，按上下文匹配稳定ID；不明确时询问身份，不轮流试号码 |
| `missing_sjhm_credential`（兼容 `missing_mobile`） | 表示选定本机身份缺字段，不代表法院登记在客户名下；`next_action=configure_selected_profile`。本人缺资料才询问保存；已确认客户接收则仅问当次后四位 |
| `missing_zjhm_credential` | 仅在用户已选择证件方式时补该人的证件后四位，不收集完整身份证、不自动切换核验方式 |
| `invalid_private_config` / `mobile_tail_conflict` | 说明本地配置问题，先修正；不当作手机号被法院拒绝 |

仅缺配置且清单中 `attempts_used=0` 时，匹配/保存后用 `--retry-identity-from "{该清单}" --lawyer-id "{已匹配ID}"` 续跑；不重新匿名探测，保留原签收状态。也可用 `--identity-stdin` 提供本次答案。**已经明确核验被拒绝的清单，只能用新的实际接收手机号后四位恢复**，不允许换一个已存律师ID继续试。

两种接续方式都保留 `--retry-identity-from`。若续跑后仍缺配置，使用**这次运行新返回的 `manifest_path`** 继续；原清单已消费，不再使用。`unknown` 表示结果不明，其清单不能作为此入口的续跑依据，应先处理服务/响应问题，不能据此换号码。

## 核验失败后的 AskUserQuestion

脚本不能自行调用宿主的问答工具；它返回可执行的 `identity.next_action`，由加载本 Skill 的 Agent 提问并接续。

1. **停止请求**：首次核验被明确拒绝时，脚本返回 `status=identity_blocked`、`identity.status=rejected`、`identity.next_action=ask_recipient_mobile_last4`。此时停止后续签收、列表和下载，不自动尝试其他凭据；此前的匿名探测已发生。签收是否已发生以清单receipt为准，不能把核验失败解释为一定未签收。
2. **询问并等待真实回答**：

   > 当前配置的手机号未通过这条送达链接的核验。请提供该短信实际接收手机号的后四位（4位数字）；客户转发的短信请填写客户实际接收号码的后四位。

   API已要求核验、且已知是客户短信没有可用凭据时，问同一个问题，省略“当前配置未通过”。使用宿主**当前可用且支持自由文本**的 `AskUserQuestion` / 等效问答工具。工具不可用、不支持自由输入或当前模式不允许时，以一条普通问题结束本轮并等待；不能把超时、空回答或默认选项当成后四位。不要为了提问切换模式或修改宿主配置。
3. **检查并传入答案**：只接受4位 ASCII 数字字符串，保留前导零；缺位、字母或空输入在本地重新询问，不请求法院。默认用 `--identity-stdin` 将 `{"mobile_last4":"用户提供的4位数字"}` 作为 stdin 输入；不修改律师配置、不建立客户长期配置、不在输出或清单回显后四位。
4. **接续原任务**：对被明确拒绝或缺配置的清单指定 `--retry-identity-from "{上次manifest_path}"`，沿用原链接、输出根目录和已获得的签收授权。正常下载模式在同一 HTTP 会话中完成核验与后续下载；不先跑只核验再重复跑完整流程。原本只要求核验时保留 `--identity-only`。未授权签收时不加 `--confirm-receipt`，已有授权无需再问；清单中confirmed/unconfirmed/unknown签收状态会被继承，不重发。
5. **再次失败就停止**：续跑累计最多2次核验。第二次被拒绝返回 `next_action=check_delivery_registration`，提示核对法院登记号码或联系法院；不继续问第三组后四位、不轮流试配置。未知响应、超时、服务错误与号码拒绝分别处理，不能借服务故障索取更多个人资料。

恢复命令形状如下，真实答案通过调用方的 stdin 传入：

```bash
python3 scripts/download_zxfw.py \
  --url "{原始送达链接}" \
  --identity-stdin \
  --retry-identity-from "{失败清单的manifest_path}" \
  --output /tmp/court-sms-staging/
```

`--identity-stdin` 不与 `--lawyer-id` 混用，避免把客户输入错误归到律师名下。客户后四位已随短信给出时可传入该入口；正常首次运行仍先尝试匿名列表，确需核验才使用答案，不需要先制造一次失败，也不需要 `--retry-identity-from`。

真实答案通过工具的标准输入或程序的 `subprocess.run(..., input=json.dumps({"mobile_last4": answer}), text=True)` 传入，不用 `echo`/`printf` 把答案拼进 shell 命令。

续跑清单通过链接参数摘要匹配同条送达，记录累计次数，不保存后四位。同一失败或缺配置记录只能接续一次；其副本也共享原记录的 `.retry-used` 标记，即使响应不明也不自动重放。它是本次工作流的重试控制，不代表法院的真实锁定阈值；不得新开运行绕过已耗尽的预算。

## 用户要求长期保存后四位时

只有用户明确要求复用该人的资料时，才保存客户 `mobile_last4`：

```bash
python3 scripts/lawyer_config.py set-tail \
  --lawyer-id recipient-a --name "受送达人姓名" --stdin
```

输入为 `{"mobile_last4":"用户提供的4位数字"}`，默认不回显；不接收完整手机号或其他字段。不同身份用不同ID，不能覆盖本人配置。`mobile` 与 `mobile_last4` 同时存在时必须一致；冲突会拒绝写入并保留旧配置。证件后四位方式仅在用户明确选择时使用，不作手机号失败后的自动回退。

## 官网流程与授权

2026-11-04 核对的法院公开静态资源：

- `getSfhyKg`：请求含 `qdbh/sdbh/sdsin`，有 `mm` 时保留；`code=200` 且 `data=true` 或 `"true"` 时要求核验。
- `checkSdryxx`：同样的链接参数，再加 `jylx=sjhm/zjhm` 与 `jyz=对应后四位`。页面默认显示证件方式，支持切换手机号。
- 本下载器使用同一 Cookie 会话；正常先匿名探测，确需核验才核验，已授权才签收并刷新列表下载。未授权时省略签收接口。官网页面在取得列表后会发送签收；未授权签收时不能用该页面回退。
- `--identity-only` 只调用核验开关与核验接口，不取列表、不下载，也不发送签收；即使带了 `--confirm-receipt` 也不会签收。

核验与签收响应不能单独确定法律送达日。客户短信涉及代为签收时，沿用户对该次任务的明确授权处理，不由后四位输入推断签收授权。

## 状态与失败处理

| 结果 | 接续动作 |
|---|---|
| `identity.status=not_requested` | 匿名API可读，未提交任何后四位，继续已授权范围内下载 |
| `identity.status=not_required` | 仅只核验模式中开关关闭，不索取手机号 |
| `status=needs_config` | 缺本人配置时询问并保存；客户短信改用单次后四位入口；非法或冲突配置先修正，不请求法院 |
| `next_action=ask_recipient_mobile_last4` | 执行上述问答，收到答案后携带失败清单续跑 |
| `next_action=check_delivery_registration` | 本次预算耗尽，停止并提示核对登记 |
| `identity.status=unknown` | 停止签收和列表，检查服务或响应；不当作号码错误、不猜凭据 |
| `status=identity_checked` | 只核验模式通过或不需核验，尚未下载 |
| `status=downloaded` | 所有返回文书通过基础检查；继续归档、解析及送达证据核对 |

`config/lawyers.json` 属于本机私有文件，多位律师共用同一系统账号或 Skill 安装时，按ID区分不构成账号隔离；需要隔离时使用各自系统账号和受控安装目录。

## 来源与验证边界

- [法院公开页面入口](https://zxfw.court.gov.cn/zxfw/)。
- [入口脚本 index.98125694.js](https://zxfw.court.gov.cn/zxfw/static/js/index.98125694.js)：配置身份核验端点。
- [送达共用脚本 c1821102.js](https://zxfw.court.gov.cn/zxfw/static/js/pagesAjkj-app-wssd-index~pagesAjkj-common-wssd-index.c1821102.js)：四位输入、方式切换和核验调用。

脚本名是2026-11-04的核对快照，不作为永久入口。2026-11-04 一条真实链接的手机号核验、未签收下载、授权签收及下载成功；2026-11-05 又用同一链接的新无Cookie请求确认：网页显示核验且开关true，API仍能只凭原链接参数下载，无需手机号。该链接此前已有处理记录，不能据此证明全新未处理送达也接受未签收下载。失败问答与续跑使用本地合成回归及独立离线演练验证，不向真实链接故意提交错误后四位。其他平台、验证码及跨模型长期稳定性仍为 `NOT_VERIFIED`。
