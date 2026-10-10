# CHANGELOG

## 0.2.0 (2026-10-09)

- **登录态持久化固化为核心设计**：新增「浏览器会话与登录态管理」节——持久 profile（法穿 launch_persistent_context 同构）、登录 cookie 实测有效期一年（gehCYwtM3CvqO httpOnly）、验证标记七天（gehCYwtM3CvqP）、登录态以 cookie 判定不以页面 UI 为准
- 新增 `scripts/ensure_chrome.sh`：幂等工位管理（CDP 活着复用绝不重启，未跑才启动持久 profile Chrome）
- `cdp_ems.js` 反风控升级：trustedFill/trustedClick（Input.insertText / dispatchMouseEvent，isTrusted=true）——合成事件被 EMS 风控识别（弹验证+重置登录 UI）的教训修复；修复首页 /?to= 重定向 URL 误判为查询页的导航 bug
- query-flows.md 新增 §0 cookie 机制与 §0.5 trusted 输入铁律

## 0.1.0 (2026-10-09)

- 初版：登记（add-mailing）→ 官网轨迹查询（CDP Chrome）→ 时间戳+URL 水印 PDF 入 08 目录 → set-mailing 回写
- EMS 流程实测（11183 查询页、安全验证墙、查询按钮 JS 精确点击）；CDP printToPDF 水印方案实测
- 顺丰流程从 FachuanHybridSystem express_query 移植（未实测，待首次使用校正）
- 上游配套：case-progress schema §2.17 邮寄跟踪节 + add-mailing/set-mailing 子命令
