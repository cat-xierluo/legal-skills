# md2word 任务清单

## 已完成

### Task-008：自然语言示例框的书籍出版渲染

- **状态**：✅ 已完成（待跨仓 PR 合并）
- **目标**：为 AI 原始输出等自然语言样例新增语义围栏，使其阅读节奏接近正文，仅以浅灰背景区隔；保留既有 `text` 代码框行为。
- **范围**：`scripts/md2word.py` 的围栏分派与示例框渲染、`book-publish` 配置、回归测试和使用说明。
- **非目标**：不批量转换现有 `text` 围栏；不调整一般代码块、Markdown 引用块或全书正文。
- **验收证据**：`python3 -m unittest skills/md2word/scripts/test_regressions.py -v` 通过 17/17；新增回归核对示例框底纹、真实 cell margins、正文 12pt / 1.5 倍行距，以及 `text` 的 Courier New 9pt / 1.2 倍行距兼容性。
- **关联**：DEC-015；法律 AI Skill 书 T205 的窄范围第十一章预览。
