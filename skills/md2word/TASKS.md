# md2word 任务清单

## 已完成

### Task-008：代码框与正文的外部垂直间距

- **状态**：✅ 已完成（待跨仓 PR 合并）
- **目标**：为所有代码围栏增加与前后正文的外部间距，同时保持框内既有代码样式不变。
- **范围**：`scripts/md2word.py` 的首末段间距、`book-publish` 配置、回归测试和使用说明。
- **非目标**：不新增围栏语言；不调整代码框的字体、字号、底纹、边框、左右缩进或框内行距。
- **验收证据**：`python3 -m unittest skills/md2word/scripts/test_regressions.py -v` 通过；新增回归核对三行 `text` 框首行前 6pt、末行后 6pt、中间行 0，并保持 Courier New 9pt / 1.2 倍行距和既有底纹。
- **关联**：DEC-015；法律 AI Skill 书 T205 的窄范围第十一章预览。
