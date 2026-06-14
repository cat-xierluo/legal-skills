# 变更记录

## [1.4.3] - 2026-06-14

### 🔥 真修:`httpx.Client(..., trust_env=False)` 全 5 处加固 — cron 死循环 root cause 治本

> 经过 1.4.1(3 处 except 探针)+ 1.4.2(入口兜底)+ `book-ocr-manager 0.6.9`(信道扩宽)
> 三层诊断铺路,用户第七次手测拿到完整 traceback,锁定真因:**httpx 默认 `trust_env=True`,
> 会从环境变量 `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY` 读 proxy URL 构建 mounts**。
> cron / Agent 沙箱子进程下,proxy env 可能含畸形值(用户 `~/.zshrc` 写:
> `HTTPS_PROXY=http://127.0.0.1:$_opencode_proxy_port`,变量未定义时展开为 `http://127.0.0.1:`),
> httpx 在 `_urlparse.py:411 normalize_port` 抛 `InvalidURL: Invalid port: ':1]'`,
> 100% 阻塞 OCR 调用。

### 修复

5 处 `httpx.Client(...)` / `httpx.get(...)` **全部加 `trust_env=False`**:

- `paddle_ocr.py:413` `_make_request._post`(同步提交)
- `paddle_ocr.py:526` `_submit_async_job._post`(异步提交)
- `paddle_ocr.py:558` `_poll_async_job` 客户端(轮询 + JSONL 下载)
- `mineru_ocr.py:218` `_self_test` 直调 `httpx.get`(token 自检)
- `mineru_ocr.py:245` `_client()`(MinerU 所有请求公用客户端)

### 为什么 `trust_env=False` 合适

- legal-ocr 调的是 **公网 API**(`paddleocr.aistudio-app.com` / `mineru.net`),**不应该走本机代理**
- 代理对内网 / 翻墙服务才有意义;公网 API 走 socks/http proxy 只会带来污染风险
- `trust_env=False` 是 httpx 推荐的"程序化 client"标准做法
- 不影响手动跑(手动跑用户已无 proxy env 时本来就 OK);只在 cron / Agent 沙箱下提供保护

### 决定性验证(本地复现)

```bash
# 修复前:必抛
$ HTTPS_PROXY="http://127.0.0.1:1]" python3 -c "import httpx; httpx.Client(timeout=30)"
InvalidURL: Invalid port: '1]'

# 修复后:exit=0,2 个 backend 自检通过
$ HTTPS_PROXY="http://127.0.0.1:1]" uv run --script scripts/convert.py checktoken
legal-ocr 配置自检
===============================================
MinerU: Token 自检通过…
PaddleOCR: 已检测到必要配置。
```

### 建议用户做的清理

修复后,之前**所有被 `Invalid port: ':1]'` 击败的 segments**(SQLite `segments.status='failed' AND last_error LIKE '%Invalid port%'`)都不再是真失败,可以批量重置为 `planned`(本机统计约 7264 段 / 1501 本书)。详见 `book-ocr-manager` 同步 bump 到 `0.6.10` 的 CHANGELOG。

### 关联

- TASKS.md(book-ocr-manager)5 号问题第 127-153 行:用户第七次手测的 traceback 是真因锁定的关键证据
- 1.4.1 / 1.4.2 的探针都保留(覆盖未来其他类型错误);本版加 `trust_env=False` 是定向治本
- DEC-025(待写):本版决策矩阵 + 复现剧本 + 7264 段重置建议

## [1.4.2] - 2026-06-14

### 入口级兜底 catch — 1.4.1 探针的补完

> 背景:1.4.1 在 3 处 httpx 调用点装的 `except httpx.InvalidURL` 在 cron 跑批时**全没触发**。
> 说明真因更早(可能在 `PaddleOCRBackend.__init__` / `MinerUBackend.__init__` /
> `route.choose_backend` 等阶段就抛了),绕过了内部 catch。

- **`convert.py:__main__`** — `raise SystemExit(main())` 改为 `try ... except BaseException: traceback.print_exc(file=sys.stderr); raise SystemExit(1)`,**入口层兜底**:不管哪行抛错,完整 stack trace 必进 stderr。
- 与 1.4.1 的 traceback dump 行为重叠时不冲突(SystemExit 直接 re-raise,不进 catch 块;真正异常都被入口 catch 兜底)。
- 配合下游 `book-ocr-manager 0.6.9` 的 `run_ocr.py:326` 信道扩宽(从只抓 stderr 最后一行改为抓后 30 行),下次 cron 触发的 `events.message` 必含完整 traceback。

### 用户感知

下次 OCR 失败时,SQLite `events.message` 不再是 24 字符短文案,而是含完整 stack trace,例如:

```
convert.py 入口异常:InvalidURL: Invalid port: ':1]'
Traceback (most recent call last):
  File ".../convert.py", line ..., in <module>
    ...
  File ".../paddle_ocr.py", line ..., in __init__
    ...
httpx.InvalidURL: Invalid port: ':1]'
```

直接锁定真正抛错的文件 + 行号 + 完整调用栈。

### 关联

- 1.4.1 加的 3 处 except 仍保留(覆盖典型场景),本版只在入口加兜底
- `book-ocr-manager` 同步 bump 到 `0.6.9`,加配套信道扩宽
- 烟雾测试:`convert.py --help` / `convert.py checktoken`(本机 + 模拟空 PATH 两种 env) 均正常 exit=0

## [1.4.1] - 2026-06-14

### 诊断性 logging 增强(不改业务逻辑)

> 背景:`book-ocr-manager` cron 大批 OCR 失败,所有 `events.message` 都是 24 字符短文案 `"最后错误:Invalid port: ':1]'"`,
> 无法定位是 PaddleOCR / MinerU 哪个 backend、哪一行 httpx 调用、哪个 url 抛的。
> 根因是 `convert.py` 把 `str(last_error)` dump 到 stderr,抹平了 type 和 traceback。

- **`convert.py`**:`print(f"最后错误:{last_error}")` 改为先打印完整 `traceback.format_exception(...)`,末行保留旧前缀但补 `type(last_error).__name__`(让上游 `run_ocr.py:326` 抓 stderr 最后一行时能看到异常类,如 `httpx.InvalidURL`)
- **`paddle_ocr.py:_poll_async_job`**:`client.get(jsonl_url)` 增加 `except httpx.InvalidURL`,失败时 `raise RuntimeError(f"... jsonUrl={jsonl_url!r} ...")` — `jsonl_url` 来自 PaddleOCR 服务端响应 `data.resultUrl.jsonUrl` 字段,是可疑的畸形 URL 来源之一
- **`mineru_ocr.py:_download_zip_and_extract`**:`client.get(result_url)` 增加 `except httpx.InvalidURL`,失败时带 `full_zip_url` 真值 raise
- **`mineru_ocr.py:_upload_via_ticket`**:`client.put(upload_url, ...)` 增加 `except httpx.InvalidURL`,失败时带 `file_urls[0]` 原值 + `normalize 后` 同时输出 — `_normalize_upload_url` 不做 URL 校验,是 **最高嫌疑点**

### 用户感知

下次 `Invalid port` 复现时,`events.message` 末尾会变成类似:

```
最后错误:RuntimeError: MinerU 上传 URL 非法:file_urls[0]='...' normalized='...' (httpx.InvalidURL: Invalid port: ':1]')
```

或 PaddleOCR 路径:

```
最后错误:RuntimeError: PaddleOCR JSONL 下载 URL 非法:jsonUrl='...' (httpx.InvalidURL: Invalid port: ':1]')
```

直接锁定后端、字段、真实 URL,无需再追代码。

### 关联

- 触发分析:`book-ocr-manager` TASKS.md 第 83-106 行(2026-06-14 cron 第四次跑批 1154 段 100% Invalid port)
- 此版本只增强 logging、不改业务路径;真修复(URL 校验 / `_normalize_upload_url` 加 httpx.URL 检查)等下次 cron 触发拿到真 URL 后定向修
- 烟雾测试:`convert.py --help` / `convert.py checktoken` 均正常,语法 + import 链路无破坏

## [1.4.0] - 2026-06-06

### 改进
- 新增瞬态网络错误自动重试：所有 HTTP 调用（同步提交、异步提交、异步轮询、MinerU 上传/轮询/下载、Token 自检）通过统一的 `retry_with_backoff` 包装；DNS 失败、连接失败、读取超时等 `httpx.RequestError` 会被指数退避重试 2-3 次。
- 退避参数通过环境变量控制：`LEGAL_OCR_RETRY_ATTEMPTS`（默认 3）、`LEGAL_OCR_RETRY_BASE_DELAY`（默认 1.0s）、`LEGAL_OCR_RETRY_MAX_DELAY`（默认 30.0s）；`PADDLEOCR_RETRY_*` 与 `MINERU_RETRY_*` 可覆盖单后端。
- 重试前向 stderr 输出一行 `PaddleOCR/MinerU 瞬态错误 …` 日志，便于排查真实网络问题。

### 文档完善
- SKILL.md 新增「瞬态错误自动重试」章节，说明范围、瞬态定义、默认参数和配置项。
- `.env.example` 顶部与各后端小节均补充 RETRY_* 变量。

## [1.3.3] - 2026-06-05

### 修复
- PaddleOCR 同步接口新增返回页数校验：当 `result.dataInfo.numPages` 或 `result.dataInfo.pages` 长度少于本地 PDF 批次页数时，转换直接失败并提示降低 `PADDLEOCR_BATCH_PAGES` 或使用 `--pages` 重跑。

### 改进
- PaddleOCR 批次元数据新增 `expected_pages` 和 `returned_pages`，便于排查大 PDF 缺页、服务端单次返回上限等问题。

### 文档完善
- 在 `SKILL.md` 故障排除中补充“PaddleOCR 返回页数不足”的处理方式。

## [1.3.2] - 2026-06-03

### 优化
- archive 不再单独保存输入副本：移除 `archive/<时间戳>_<名称>/input/` 目录及对应的 `shutil.copy2` / `source_url.txt` 写入逻辑。
- 输入文件元信息继续保留在 `metadata.json` 的 `source` 字段：本地文件记录 `path` / `sha256` / `size_bytes`；远程 URL 记录原始字符串。
- 同步更新 `SKILL.md` 与 `references/output_schema.md` 的 archive 结构说明。

### Reason
- 现状：`skills/legal-ocr/archive/` 累计 649 MB；6 个 archive 平均 100 MB+，主要来自 `input/` 下的原 PDF 副本。
- 风险：随着 OCR 任务增多本地磁盘会持续膨胀；archive 已在 `.gitignore` 内，不会被 push，但本地占用无法控制。
- 取舍：放弃 archive 内"可重放原文件"的能力，换取固定占用；如需重新转换，使用 `metadata.json.source.path`（本地）或 `metadata.json.source.raw`（URL）重跑即可。

## [1.3.1] - 2026-05-20

### 文档完善
- 精简 SKILL.md frontmatter description，仅保留 OCR/扫描识别/文档识别等功能触发条件和必要边界，不再描述后端路由等实现细节。
- 同步 README 与 marketplace 中的 `legal-ocr` 简介。

## [1.3.0] - 2026-05-20

### 改进
- 将技能定位调整为“通用 OCR + 法律材料自动增强”：用户需要 OCR、扫描识别、图片文字识别或文档识别时可直接调用，非法律材料默认保持通用 OCR 输出。
- `LEGAL_OCR_LEGAL_TERMS` 默认改为 `auto`，仅在检测到法院文书、案号、当事人标签、判决/裁定结构等法律信号时启用法律术语优化。
- 新增 `--legal-terms auto|always|never` 参数，支持单次自动、强制或关闭法律术语优化。
- `result.json` 与 `metadata.json` 新增法律上下文检测记录，便于复核为什么启用或跳过法律增强。

### 文档完善
- 更新 `SKILL.md` 触发条件，明确可替代普通 OCR 场景，并说明法律增强的自动检测机制。
- 更新 `.env.example`、`references/output_schema.md` 和 `references/legal_terms.md`，同步 `auto` 模式说明。

## [1.2.2] - 2026-05-20

### 技术优化
- 按 `skill-lint` 规范扁平化 `scripts/` 目录，移除 `scripts/backends/` 与 `scripts/postprocess/` 子目录。
- 优化脚本依赖防护，缺少 `httpx` 或 `pypdfium2` 时给出清晰安装提示。
- 优化 `SKILL.md` frontmatter 描述，明确触发场景和不适用边界。

### 文档完善
- 补充 Python 包依赖表和输入/输出说明。

## [1.2.1] - 2026-05-20

### 改进
- 法律术语断字合并支持跨单个换行，处理 `本院认\n为`、`人\n民\n法\n院` 等 OCR 断行场景。
- 新增保守型 OCR 硬换行整理，合并明显属于同一中文段落的物理换行，同时保留标题、当事人标签、编号、表格和 Markdown 结构。
- 扩充常见法律词表，补充审理经过、争议焦点、执行标的、案件受理费、迟延履行期间等常见文书词。
- 新增 `LEGAL_OCR_LINE_MERGE` 与 `--no-line-merge`，可关闭硬换行整理。

### 文档完善
- 补充换行整理边界说明，强调不做事实改写和过度纠错。

## [1.2.0] - 2026-05-20

### 新增
- 新增保守型法律术语优化后处理，默认修正常见 OCR 断字、异体字和法律文书标签格式。
- 新增自定义术语文件支持，可通过 `LEGAL_OCR_CUSTOM_TERMS_PATH` 加载 JSON 替换表。
- 新增 `--no-legal-terms` 参数，可单次跳过法律术语优化。
- 新增 `references/legal_terms.md` 与 `config/legal_terms.example.json`，说明默认处理范围和自定义格式。

### 改进
- 后处理顺序调整为先做法律术语优化，再做标题和条文结构整理，提升 `本院认为`、`判决如下` 等文书结构识别稳定性。
- 法律术语替换记录写入 `postprocess_log.json`，并保留 `result_raw.md` 便于人工复核。

## [1.1.1] - 2026-05-20

### 改进
- 自动路由调整为配置优先：只配置 PaddleOCR 时优先使用 PaddleOCR，只配置 MinerU Token 时所有支持输入统一走 MinerU，两套 API 都配置时再按材料类型选择最优后端。
- 两套 API 都配置时保留候选后端；首选后端失败后可自动尝试下一后端。
- 转换失败记录新增错误分类，支持识别额度/频率限制、鉴权失败、轻量接口超限、不支持类型、超时和网络问题。

### 文档完善
- 补充自动分流说明，明确当前额度判断来自 API 响应码和错误信息，暂未接入独立额度预检接口。

## [1.1.0] - 2026-05-20

### 新增
- 复制旧 `paddle-ocr` 与 `mineru-ocr` 的本地 `.env` 配置到 `legal-ocr/config/.env`，保留原 Token 和后端设置；该文件继续被 Git 忽略。
- PaddleOCR 后端新增 `pdf-processor` 同源能力：兼容 `PADDLE_OCR_API_ENDPOINT` / `PADDLE_OCR_API_KEY` / `API_URL` / `TOKEN` 变量别名。
- PaddleOCR 后端新增异步任务协议支持，可调用 `/api/v2/ocr/jobs` 并轮询 JSONL 结果。
- 新增 `PP-OCRv5` 与 `PaddleOCR-VL-1.5` 模型选择，支持 `--paddle-model` 参数和 `PADDLEOCR_MODEL` 配置。
- 新增 PaddleOCR optionalPayload 扩展：支持 VL 版面检测、图表识别、方向/去畸变、文本行方向、可视化和额外 JSON payload。

### 改进
- `checktoken` / smoke test 可识别 PaddleOCR 旧变量和 `pdf-processor` 变量别名。
- PaddleOCR archive 中记录 API 协议、模型、轮询参数和 payload 配置。

## [1.0.0] - 2026-05-20

### 新增
- 新增 `legal-ocr` 统一 OCR Skill，整合 PaddleOCR 与 MinerU 双后端。
- 新增自动路由：本地 PDF/图片默认走 PaddleOCR，Office 文档、远程文档 URL 和网页 URL 默认走 MinerU。
- 新增统一 Python 主入口 `scripts/convert.py`，支持 `--backend`、`--output`、`--pages`、`--archive-name`、`--no-archive`、`--no-post-process`、`--model`。
- 新增 MinerU Python 后端，覆盖 local/token、local/light、remote/token、remote/light 四条转换链路。
- 新增 PaddleOCR Python 后端，保留本地 PDF 自动分批、图片提取和 Markdown 输出能力。
- 新增统一 archive 结构，保留输入、最终 Markdown、原始 Markdown、结构化 JSON、后端原始结果和元数据。
- 新增基础法律后处理，支持空行清理和简单法律标题结构识别。
- 新增 `scripts/smoke_test.py` 和 JXA 兼容入口 `scripts/convert.js`。

### 文档完善
- 新增 `SKILL.md`、`references/output_schema.md`、`TASKS.md`、`DECISIONS.md` 和 `LICENSE.txt`。
- 新增统一 `.env.example`，保留 `PADDLEOCR_*` 与 `MINERU_*` 变量名并补充 `LEGAL_OCR_*` 设置。

### 待办事项
- 增加真实法律 PDF、病历、票据和网页 URL 的回归样本。
- 评估复杂法律词典纠错、印章标注和图表标注规则。
