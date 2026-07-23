# 更新日志

## [1.0.0] - 2026-07-11

### 新增

- 建立 source → render → independent visual review → DOCX page render → release 的 fail-closed 状态链。
- 用 `requirements.yaml` 把规则映射到 verifier、scope、阈值和阻断属性；空规则、空 scope、未知 verifier 与未实现阶段一律失败。
- 候选哈希覆盖 Markdown 与项目声明的所有 SVG/图片表示；证据同时绑定规则文件、PNG、DOCX、PDF 与 reviewer JSON hash。
- 全量内联 SVG 经 librsvg 渲染，检测 XML、透明底、`style`/`font-family`、marker、端点距离、空白图与可见 bbox 留白。
- 最终 DOCX 优先绑定 Microsoft Word/WPS 导出的 PDF，再由 Poppler 逐页转 PNG；没有作者引擎 PDF 时仅允许通过中文字符比、bigram 与“文字 bbox 对应栅格墨迹”三重保真校验的 LibreOffice fallback，避免文字层仍在但可见中文全部丢失时假验收。
- 检查 OOXML 包、脚注 Markdown 残留、中文 ASCII 引号、图片覆盖、页边距、字体与分页边缘裁切。
- 生成 contact sheets 与逐 artifact review template；支持多个 fresh-context reviewer 分批填写，强制 producer/reviewer 分离、逐图逐维度覆盖和 hash 新鲜度。
- 新增故障注入回归，覆盖空规则绿灯、空项目、Mermaid、中文 ASCII 引号、相邻图片、旧证据、自审、SVG archive 漂移及 DOCX 脚注星号。

### 修复

- 修复 0.1.0 候选实现把已知 ASCII 引号降为非阻塞 PARTIAL 后仍返回成功的问题。
- 修复 `--stage png/docx` 在没有任何 requirement 时返回成功的问题。
- 修复 candidate hash 只覆盖 Markdown、status 不校验陈旧证据、scope/threshold 未执行等 fail-open 路径。

### 文档完善

- 增加独立视觉 reviewer 协议；明确 contact sheet 只定位，必须打开原尺寸 PNG，作者不承担逐图人工兜底。

## [0.1.0] - 2026-07-11

### 技术预研

- 建立 acceptance harness 五支柱与 Markdown 阶段概念验证。该版本没有 SVG/PNG/DOCX/独立 reviewer 回归能力，已由 1.0.0 supersede，不具备 release 放行资格。
