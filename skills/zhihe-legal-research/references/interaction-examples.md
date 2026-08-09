# 智合法律研究 - 交互示例

本文档展示各种使用场景下的完整交互流程。

---

## 场景一：标准流程（用户主动查询）

用户提问 → 提交问题 → 用户稍后查询 → 查看结果

```
用户：劳动合同到期不续签需要赔偿吗？

你：[执行 ./scripts/auth.sh check → 登录有效]
    [执行 ./scripts/research.sh submit "劳动合同到期不续签需要赔偿吗？"]
    [获得 task_id: a1b2c3d4]

    回复：
    ✅ 您的法律问题已提交，后台正在进行调研分析。
    ⏱️ 预计需要 3-4 分钟完成。
    📋 任务 ID：`a1b2c3d4`

    👉 请在约 4 分钟后回复"查看结果"来获取分析报告。

--- 用户等待约 4 分钟 ---

用户：查看结果

你：[执行 ./scripts/research.sh status a1b2c3d4 → completed]
    [执行 ./scripts/research.sh result a1b2c3d4 → 获取文字结果]
    [执行 ./scripts/research.sh report a1b2c3d4 → 获取报告链接]
    [执行 ./scripts/research.sh archive a1b2c3d4 → 自动归档]

    回复：
    📋 **法律分析结果：**

    根据《劳动合同法》第四十六条的规定，有下列情形之一的，用人单位应当向劳动者支付经济补偿...

    （完整分析文本）

    📄 **详细报告：**
    [点击下载完整法律研究报告](https://...)
    文件名：法律研究报告_20260310_143530.docx

    📁 已自动归档到 archive/ 目录。
```

---

## 场景二：Claude Code 后台监控模式

适用于 Claude Code 环境，自动监控无需用户手动查询。

```
用户：帮我查一下商标侵权的赔偿标准，好了直接告诉我

你：[提交问题 → 获得 task_id: xyz789]
    [使用 Bash 工具启动后台监控]

    Bash 工具参数：
    - command: "/path/to/scripts/monitor.sh monitor xyz789 600 30"
    - run_in_background: true
    - timeout: 600000

    回复：
    ✅ 您的法律问题已提交，后台正在进行调研分析。
    ⏱️ 预计需要 3-4 分钟完成。
    🔄 后台自动监控中，完成后会主动通知您。

    [等待后台监控完成...]

    收到后台任务完成通知后：

    回复：
    ✅ 您的法律研究已完成！

    📋 **法律分析结果：**
    ...

    📄 **详细报告：**
    [下载链接]
```

---

## 场景三：首次使用需要登录

```
用户：帮我研究一下竞业限制的法律问题

你：[执行 ./scripts/auth.sh check → Token 不存在]

    回复：
    我来帮您进行法律研究。首次使用需要验证身份。

    请提供您的手机号码（需要智合AI平台会员账号）。

用户：13800138000

你：[执行 ./scripts/auth.sh send-code 13800138000]
    [验证码已发送]

    回复：
    验证码已发送至 138****8000，请输入收到的6位验证码。

用户：123456

你：[执行 ./scripts/auth.sh verify 13800138000 123456]
    [登录成功，Token 已保存]

    回复：
    ✅ 登录成功！您是豪华版会员。

    现在为您提交法律研究问题...

    [执行 ./scripts/research.sh submit "竞业限制的法律问题"]
    [获得 task_id]

    ✅ 您的法律问题已提交。
    👉 请在约 4 分钟后回复"查看结果"。
```

---

## 场景四：Token 过期需要重新登录

```
用户：查看结果

你：[执行 ./scripts/research.sh status <task_id>]
    [返回 401 错误]

    回复：
    您的登录凭证已过期（有效期72小时），需要重新登录。

    请提供您的手机号码。

用户：13800138000

你：[重新执行登录流程...]
```

---

## 场景五：结果还没完成

```
用户：查看结果

你：[执行 ./scripts/research.sh status <task_id>]
    [状态：running]

    回复：
    ⏳ 您的法律研究还在处理中，请再等 1-2 分钟后再发送"查看结果"。
```

---

## 场景六：非会员用户

```
用户：帮我研究一个法律问题

你：[执行 ./scripts/auth.sh check]
    [is_vip: false]

    回复：
    抱歉，法律研究服务需要智合AI平台会员资格。

    您可以访问 https://www.zhiexa.com 开通会员后继续使用。
```

---

## 场景七：用户不记得 task_id

```
用户：结果出来了吗

你：[不确定 task_id，执行 ./scripts/research.sh history 1 3]
    [获取最近任务列表]
    [找到最近未完成的任务: xyz789]
    [执行 ./scripts/research.sh status xyz789]
    [状态：completed → 获取结果并归档]

    回复：
    找到您最近的研究任务，结果如下：

    📋 **法律分析结果：**
    ...
```

---

## 场景八：查看历史记录

```
用户：我之前研究过什么法律问题？

你：[执行 ./scripts/research.sh history 1 10]

    回复：
    📜 **您的历史研究记录：**

    1. 劳动合同到期不续签需要赔偿吗？
       状态：已完成
       时间：2026-03-10 14:30

    2. 商标侵权的赔偿标准
       状态：已完成
       时间：2026-03-09 10:15

    ...

    如需查看某个研究的详细结果，请告诉我对应的序号。
```

---

## 场景九：研究失败或超时

```
用户：查看结果

你：[执行 ./scripts/research.sh status <task_id>]
    [状态：failed 或 timeout]

    回复：
    ❌ 您的法律研究遇到了问题（失败/超时）。

    建议您：
    1. 简化问题后重新提交
    2. 将复杂问题拆分为多个小问题
    3. 稍后重试

    是否需要重新提交？
```

---

## 脚本命令速查

| 场景 | 命令 |
|------|------|
| 检查登录状态 | `./scripts/auth.sh check` |
| 发送验证码 | `./scripts/auth.sh send-code <phone>` |
| 验证登录 | `./scripts/auth.sh verify <phone> <code>` |
| 提交问题 | `./scripts/research.sh submit "<query>"` |
| 查询状态 | `./scripts/research.sh status <task_id>` |
| 获取结果 | `./scripts/research.sh result <task_id>` |
| 获取报告 | `./scripts/research.sh report <task_id>` |
| 归档结果 | `./scripts/research.sh archive <task_id>` |
| 查看历史 | `./scripts/research.sh history [page] [size]` |
| 登出 | `./scripts/auth.sh logout` |
