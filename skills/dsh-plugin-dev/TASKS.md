# DSH Plugin Dev 任务

## 2026-10-31 官方 rc.5 并行 Desktop 验收法回写

- [x] 核对既有并行实例配方：`--user-data-dir` 可与生产实例并存，但旧文缺少同 bundle 多进程下的实例定位与授权凭据边界。
- [x] 回写官方 `0.2.1-rc.5` 实测：独立 `DSH_HOME` + 独立 userData；原生 CUA 不用于同 bundle 多实例选择，改用测试实例独占 loopback DevTools 目标；只关闭本任务 PID 并等待 Host/端口消失。
- [x] 明确生产凭据默认零接触；用户明确授权免登录时才做最小账号/API/provider 快照，保留隔离 browser-session，不输出明文或写生产配置。
- [x] 登记 rc.5 `dsh-app://` shell 转发停滞的判别边界：先区分官方代理层与插件 fetch route，插件侧只做有界超时，不宣称修复上游。
- [x] 验证：skill-lint security/harness 静态审查均 PASS，`test-lint.mjs` 47 项自测 PASS；通用 quick_validate 不兼容本仓既有发布 frontmatter（author/homepage/version），该失败与本次候选无关，版本与 CHANGELOG 已人工对齐。
- [x] 独审返修：授权复用明确为“解析点名记录/引用/env 键后写等值快照，不整文件搬运”；DevTools 端口启动后用 lsof 复核 loopback 监听，并说明本机进程可达、验收后关闭。README 技能表版本按发布流程另行同步，不在本候选强行半更新。

## 2026-10-16 locale 展开与覆盖审计

- [x] 固定 main 201e31015d948c288d88a9945581197493bd5d9e 重现嵌套展开假 PASS 和浅覆盖假 FAIL。
- [x] 嵌套展开、重复键、属性重叠展开转 NOT_VERIFIED；保留不相交顶层展开。
- [x] Node 24.19.0 完整 CLI 自测 47 项通过，原基线对新增反例失败；原 41 项也独立通过。
- [ ] 精确候选独立审查与 CI；仅 Draft PR，不合并、不部署。

负责人：dot 限界审计修复；原解析器修复 PR #302 作者 cat-xierluo。

边界：静态近似解析仍不是一般 JavaScript AST/执行器；本次不宣称支持全部对象覆盖语义。宿主真实安装和 UI 不属此静态规则验收。
