# 决策记录

## D-2026-06-06-01 瞬态网络错误统一自动重试

- 日期: 2026-06-06
- 背景: 90-审判-all 任务首次重试 26 段全部因 `[Errno 8] nodename nor servname provided, or not known` 失败；同一晚网络恢复后只需重跑一次即可全部成功。原 legal-ocr 把所有 `httpx.RequestError` 直接抛出，编排层只能等用户手动重试。
- 决策: 在 `scripts/common.py` 新增 `is_transient_httpx_error` / `is_transient_http_status` / `retry_with_backoff` 三个工具；PaddleOCR 与 MinerU 的所有 HTTP 入口（同步提交、异步提交、异步轮询、MinerU 上传/轮询/下载、Token 自检）改为通过 `retry_with_backoff` 包装。
- 瞬态定义: `httpx.RequestError` 全部子类（DNS、连接、读取/写入超时、协议错误、远端关闭连接）。HTTP 状态码 429 与 5xx 也视作瞬态。HTTP 4xx 立即抛出（鉴权、配额、参数错误）。
- 参数: 统一默认 3 次尝试、首次重试前 1.0s、单次重试等待上限 30.0s（指数退避）。可被 `LEGAL_OCR_RETRY_*` 统一控制，被 `PADDLEOCR_RETRY_*` / `MINERU_RETRY_*` 单独覆盖。
- 取舍: 轮询循环（`_poll_async_job` / MinerU 轮询）只把内部 `client.get` 包装 retry，外层 `for` 循环不重跑，避免一次瞬态错误导致整个任务从头开始（重新提交、重新上传）。
- 影响: 编排层无需为偶发网络问题重排；状态库 `failed` 事件真正反映业务/数据问题，而不是瞬态抖动。后续如要区分业务失败与网络失败，可在此基础上扩展错误分类。

## D-2026-06-05-01 PaddleOCR 同步结果必须校验返回页数

- 日期: 2026-06-05
- 背景: 在处理 283 页 PDF《要件审判九步法》时，PaddleOCR 同步接口接受整本上传并返回成功，但后端响应 `dataInfo.numPages` 仅为 100，实际 Markdown 只覆盖前 100 页。
- 决策: 对 PaddleOCR 同步接口结果增加页数校验。PDF 批次提交后，脚本读取本地批次 PDF 页数作为预期页数，并从后端响应 `result.dataInfo.numPages` 与 `result.dataInfo.pages` 推导实际返回页数；实际返回页数少于预期时直接失败。
- 影响: 超过服务端单次返回上限的大 PDF 不再生成看似成功但缺页的 Markdown。用户需降低 `PADDLEOCR_BATCH_PAGES` 或用 `--pages` 按较小范围重跑。

## D-2026-05-20-01 新建 legal-ocr，而不是修改旧 Skill

- 日期: 2026-05-20
- 背景: `paddle-ocr` 中已有整合路线图，目标是把 PaddleOCR 和 MinerU 合并为统一 OCR 入口，但用户明确要求生成新的 Skill，不在原两个 Skill 上修改。
- 决策: 新建 `skills/legal-ocr/`，只读取复用旧 Skill 的能力边界和实现经验，不修改 `skills/paddle-ocr/` 与 `skills/mineru-ocr/`。
- 影响: 旧入口保持稳定；新入口可独立迭代、验证和发布。

## D-2026-05-20-02 首版采用稳定整合范围

- 日期: 2026-05-20
- 背景: 完整路线图包含双后端、自动路由、法律后处理、词典纠错、印章标注等能力，一次实现风险较高。
- 决策: 首版只实现双后端、自动路由、统一配置、统一归档和基础后处理。复杂词典纠错、印章/图表深度标注登记为后续任务。
- 影响: 首版更容易验证，避免影响 OCR 主链路稳定性。

## D-2026-05-20-03 Python-first，JXA 仅保留兼容入口

- 日期: 2026-05-20
- 背景: PaddleOCR 已经 Python 化，MinerU 旧实现是 JXA 单文件，不利于双后端共享配置、路由和归档逻辑。
- 决策: 新 Skill 以 Python 为主实现，MinerU 四条链路迁移为 Python；`scripts/convert.js` 仅转调 Python 主入口。
- 影响: 代码结构更清晰，后续可以继续扩展路由、后处理和测试。

## D-2026-05-20-04 保留旧配置变量名

- 日期: 2026-05-20
- 背景: 现有用户已在旧 Skill 中配置过 `PADDLEOCR_*` 和 `MINERU_*` 变量。
- 决策: 新 Skill 保留旧变量名，并新增 `LEGAL_OCR_BACKEND`、`LEGAL_OCR_POST_PROCESS`、`LEGAL_OCR_LOG_LEVEL`。
- 影响: 用户可直接复制旧 `.env` 的值，迁移成本较低。

## D-2026-05-20-05 迁入 pdf-processor 的 PaddleOCR API 适配层，不迁入双层 PDF 叠层

- 日期: 2026-05-20
- 背景: `pdf-processor` 中 PaddleOCR API 实现更完整，包含变量别名、异步任务、模型选择、VL 参数、额外 JSON payload、JSONL 解析和双层 PDF 叠层。
- 决策: 本次迁入与 `legal-ocr` Markdown 主链路直接相关的能力：变量别名、异步任务接口、`PP-OCRv5` / `PaddleOCR-VL-1.5` 模型选择、VL 参数和 JSONL 转 Markdown。暂不迁入双层 PDF 叠层和拍照件 PDF 页面替换。
- 影响: `legal-ocr` 可以复用 `pdf-processor` 的 PaddleOCR API 配置和新版异步协议，同时保持本 Skill 的主要交付物为 Markdown + archive。

## D-2026-05-20-06 自动路由采用配置优先，而不是强规则优先

- 日期: 2026-05-20
- 背景: 用户希望 `legal-ocr` 对配置更友好：只配置一套 API 时不要让用户理解复杂路由，两套 API 都配置时再按最优方向和失败回退分流。
- 决策: `auto` 路由改为先判断已配置 API。只配置 PaddleOCR 时优先 PaddleOCR；只配置 MinerU Token 时所有支持输入统一 MinerU；两套 API 都配置时按材料类型选择首选后端，并在首选失败时尝试候选后端。
- 影响: 用户迁移成本降低；大批量 OCR 时若首选 API 返回额度、频率、鉴权、网络或服务失败，可在结果元数据中看到失败类别和 fallback 记录。

## D-2026-05-20-07 法律术语优化只做保守替换，不做事实改写

- 日期: 2026-05-20
- 背景: `legal-ocr` 面向法律材料，用户希望增加常规法律词语优化，但 OCR 后处理若过度纠错可能改变事实信息。
- 决策: 新增保守型法律术语后处理，只修正常见断字、异体字、主体标签和文书结构词；不基于上下文补全人名、案号、金额、日期或事实表述。所有替换写入 `postprocess_log.json`，并保留 `result_raw.md`。
- 影响: 提升法院文书和卷宗材料的可读性，同时保留可追溯原文，降低误改风险。

## D-2026-05-20-08 硬换行整理只处理中文段落内的明显物理换行

- 日期: 2026-05-20
- 背景: 法律 OCR 结果常把同一段落按扫描版面拆成多行，影响后续阅读和分析；但自动合并换行可能破坏当事人标签、编号、表格和标题。
- 决策: 新增保守型硬换行整理，只合并明显属于同一中文段落的物理换行；保留 Markdown 结构、表格、编号、当事人标签和文书标题。该能力可通过 `LEGAL_OCR_LINE_MERGE=false` 或 `--no-line-merge` 关闭。
- 影响: 常见卷宗段落更连贯，同时避免过度改变 OCR 后文本结构。

## D-2026-05-20-09 遵循 skill-lint 扁平脚本结构，保留 ClawHub 版本字段

- 日期: 2026-05-20
- 背景: `skill-lint` 要求 `scripts/` 目录保持扁平；同时项目 AGENTS.md 的 ClawHub 发布适配建议在 frontmatter 保留 `version` 字段。
- 决策: 将原 `scripts/backends/` 与 `scripts/postprocess/` 中的模块移动到 `scripts/` 根目录，更新内部 import；`version` 字段继续保留，作为项目发布规范对 `skill-lint` 的明确豁免。
- 影响: Skill 目录结构更符合发布审查要求，同时保持 ClawHub 版本同步能力。

## D-2026-05-20-10 定位为通用 OCR，法律增强默认自动检测

- 日期: 2026-05-20
- 背景: 用户希望 `legal-ocr` 能替代原 `paddle-ocr` 与 `mineru-ocr` 的普通 OCR 场景；只要用户需要 OCR、扫描识别、图片文字识别或文档识别，就可以调用本技能。只有识别为法律相关文件时才做法律术语优化。
- 决策: 将 `LEGAL_OCR_LEGAL_TERMS` 默认语义改为 `auto`，先根据 OCR 原文和文件名检测法律上下文；仅命中法院、案号、当事人标签、判决/裁定结构等强信号时启用法律术语优化。保留 `always` 和 `never` 模式供用户强制控制。
- 影响: 普通 OCR 结果不会默认进入法律词替换链路；法律材料仍能获得保守型术语、标签和文书结构优化，检测记录写入 `result.json` 与 `metadata.json` 便于复核。

## 工作日志

### 2026-05-20 (Codex)

- **目标:** 按 `paddle-ocr` 路线图新建统一 OCR Skill。
- **操作:** 新建 `legal-ocr` 目录，迁移 PaddleOCR 与 MinerU 核心链路，新增自动路由、基础后处理、统一归档和发布索引；随后复制旧 OCR `.env`，迁入 `pdf-processor` 的 PaddleOCR API 适配层，将路由调整为配置优先，新增法律术语优化和硬换行整理，并按 `skill-lint` 规范扁平化脚本结构；最终将法律术语优化改为自动检测，明确普通 OCR 作为默认能力。
- **结果:** `legal-ocr` 具备公开发布所需的脚本、配置、文档和索引，支持 PaddleOCR 同步/异步两类 API 协议，能记录额度/频率等失败分类后尝试候选后端；非法律材料保持通用 OCR 输出，法律材料自动启用保守术语与结构优化。
- **下一步:** 用真实法律材料样本做端到端回归测试，并继续完善复杂后处理能力。
