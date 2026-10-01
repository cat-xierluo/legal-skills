# CHANGELOG — mac-photos

## [1.0.0] - 2026-10-01

### 新增

- 技能初版：Mac 照片图库读取 + 截图筛选 + Vision OCR 全文索引 + 内容搜索 + 导出保存
- `photos_read.py` 主 CLI：`doctor`（5 项环境自检）/ `scan`（默认仅截图、增量导出与增量 OCR、4 并发）/ `search`（多词 AND/OR、上下文摘要、QuickLook 与 Finder 定位）/ `list` / `export` / `stats`
- `ocr_vision.swift`：Apple Vision 原生 OCR 工具（zh-Hans + en-US，accurate/fast 两档，逐行 JSON 输出）
- `mktext.swift`：测试图生成器，用于 doctor 的 OCR 冒烟自检
- `setup.sh` 一键安装：venv 安装 osxphotos（支持自定义 pip 镜像）+ swiftc 编译 + 自检
- 零 pip import 依赖：主脚本仅用 Python 标准库，外部工具以子进程调用

### 已验证（2026-10-01，macOS 15.7.4 / arm64）

- osxphotos 0.77.2 安装于 Python 3.14.7 venv，`--screenshot`/`--download-missing`/`--update`/`--limit`/`--filename` 参数逐一确认
- Vision OCR 中文冒烟：中英数混排「合同编号XS-2026-0918违约金50000元」识别零误差
- search/list/export 全链路以模拟工作区实测：单词命中、AND 双词、未命中提示、日期倒序、复制导出均正常
- doctor 自检可正确识别完全磁盘访问缺失并给出操作指引

### 待办事项

- 开启完全磁盘访问后实测真实图库 `scan`（含 `--filename "{uuid}_{original_filename}"` 模板与 `--download-missing` iCloud 补下载行为）
- 真实图库实测通过后收尾：发现问题按 1.0.x 迭代（README 注册已随 v1.0.0 完成）
