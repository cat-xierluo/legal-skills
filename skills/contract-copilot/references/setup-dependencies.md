# setup-dependencies

本文档说明在本地直接运行 `contract-copilot` 脚本前需要准备什么。

## 一、最小可运行前提

`contract-copilot` 是自包含 skill，不依赖外部 skill 目录。运行前提：

1. 本机需要可用的 `python3`（建议 3.9+）。
2. 需要先安装 Python 包依赖：`defusedxml`、`lxml`。

OOXML 打包、解包和校验功能已内嵌在 `scripts/ooxml/` 中，无需额外安装。

## 二、必须安装的依赖

### Python 依赖

```bash
cd contract-copilot
python3 -m pip install -r scripts/requirements.txt
```

当前 `scripts/requirements.txt` 固化的依赖为：

- `defusedxml`：XML 安全解析
- `lxml`：OOXML 节点操作

### Python 版本

建议使用 `Python 3.9+`。

原因：

- 当前脚本代码使用了内置泛型写法（如 `list[dict[str, Any]]`），低版本 Python 可能无法直接运行。

## 三、可选但推荐的系统依赖

### 1. `soffice`

用途：

- 用于 OOXML 打包后的格式校验。

说明：

- 如果本机没有 `soffice`，当前脚本会给出 warning 并跳过该校验，不会因此完全无法运行。

适合安装的场景：

- 你需要更严格地校验输出 DOCX 是否可能损坏。
- 你要把脚本纳入稳定的批处理链路。

### 2. `pwsh` 或 `powershell`

用途：

- 仅在你想用 `scripts/run_apply_review_plan.ps1` 这个 Windows / 中文路径包装器时需要。

说明：

- 如果你只运行 `python3 scripts/apply_review_plan.py`，不需要安装 PowerShell。
- 如果你在 Windows、中文路径、OneDrive / 企业网盘目录下运行，建议优先使用该包装器。

## 四、推荐安装顺序

```bash
cd /path/to/contract-copilot
python3 -m pip install -r scripts/requirements.txt
```

安装完成后，可以先用最小命令验证主入口是否可跑：

```bash
python3 scripts/apply_review_plan.py --help
```

## 五、首次直接运行示例

```bash
cd /path/to/contract-copilot
python3 -m pip install -r scripts/requirements.txt
python3 scripts/apply_review_plan.py \
  --input /path/to/contract.docx \
  --plan /path/to/review-plan.json \
  --output /path/to/contract_reviewed.docx
```

## 六、常见报错与排查

### 1. `ModuleNotFoundError: No module named 'lxml'`

排查：

- 重新执行 `python3 -m pip install -r scripts/requirements.txt`。
- 确认当前运行脚本使用的 Python 与安装依赖时的 Python 是同一个解释器。

### 2. `ModuleNotFoundError: No module named 'defusedxml'`

排查：

- 同样先执行 `python3 -m pip install -r scripts/requirements.txt`。

### 3. `Warning: soffice not found. Skipping validation.`

说明：

- 这是可接受的降级提示，不代表脚本一定失败。
- 如果你需要更强的输出校验，再安装 LibreOffice / `soffice`。

## 七、维护规则

后续只要出现以下任一变化，就必须同步更新本文档与 `scripts/requirements.txt`：

- 新增或删除 Python 包依赖
- 新增或删除关键系统命令依赖
- 运行入口发生变化（如新增新的包装器或 CLI）
