---
name: book-gate
description: 本技能应在书籍或长文出版物需要出版前验收、逐图防漏、最终 DOCX 分页复核、回归验证或 fail-closed 完成门禁时使用。它把 Markdown、内联 SVG、真实 PNG、独立视觉 reviewer 与最终 DOCX/PDF 页面绑定到同一候选哈希，缺证或失败即阻断完成。不要用于单篇文章润色、只读审稿或生成配图。
version: "1.0.0"
license: MIT
author: 杨卫薪律师（微信ywxlaw）
homepage: https://github.com/cat-xierluo/legal-skills
---

# book-gate

把“worker 说完成”降级为 candidate；只让经过成品证据验证的 candidate 获得 release 状态。不要试图靠更长 prompt 保证 Agent 永不漏项，要让漏项无法穿过验收门。

## 完成状态

按以下含义报告状态：

- worker `done`：`CANDIDATE`
- source gate 通过：`SOURCE_VERIFIED`
- SVG 全量真实渲染通过：`RENDERED`
- 独立 reviewer 按哈希逐图通过：`INDEPENDENT_VERIFIED`
- 实际 DOCX 结构与分页渲染通过：`DOCX_VERIFIED`
- SVG + 最终 DOCX 每页均有独立视觉证据：`RELEASE_VERIFIED`
- 项目上下文同步完成：项目可再标 `CLOSED`

任何 blocking requirement 缺失、无 verifier、scope 为空、verifier 报错、证据过期或 verdict 非 PASS，都保持 `BLOCKED`。禁止平均分抵消单项失败。

## 依赖

先安装一次：

```bash
python3 -m pip install PyYAML Pillow
# macOS
brew install librsvg poppler
# 没有 Microsoft Word/WPS 导出的 PDF 时，fallback 需要 LibreOffice
brew install --cask libreoffice
```

脚本会检查依赖并明确失败，不会因缺工具而静默跳过。

## 工作流

设定路径：

```bash
GATE=/path/to/book-gate/scripts/book-gate.py
ROOT=/path/to/book-project
REQ="$ROOT/book-gate.yaml"
OUT="$ROOT/.book-gate-evidence"
```

### 1. 验证源稿

```bash
python3 "$GATE" verify "$ROOT" --requirements "$REQ" --stage source --out "$OUT"
```

同时检查 Markdown、内联 SVG 与项目配置；候选哈希包含 `hash_inputs` 中的所有表示。空规则、空 scope、Mermaid、中文 ASCII 引号、相邻图无承接、断图、悬空脚注、SVG 语法/marker 问题均阻断。

### 2. 生成真正的视觉审查包

使用作者实际查看的最终 DOCX。优先由 Agent 通过 Computer Use 在 Microsoft Word/WPS 中导出同版 PDF；这是排版引擎的机器可读快照，不是让作者逐页检查：

```bash
python3 "$GATE" verify "$ROOT" \
  --requirements "$REQ" \
  --stage prepare \
  --docx /path/to/final.docx \
  --pdf /path/to/word-or-wps-export.pdf \
  --producer-id <worker-or-branch-id> \
  --out "$OUT"
```

如果当前环境无法操作 Word/WPS，可暂时不传 `--pdf`，脚本会用 LibreOffice fallback；但只有 PDF 中文文字层与 DOCX 达到配置的字符比、bigram 覆盖阈值，且 PDF 声称存在的中文词框在页面 PNG 中确有可见墨迹时才继续。字体缺失导致“文字层还在、页面上的中文正文实际丢失”会直接阻断，不得拿失真分页包做审查。

该命令必须完成四件事：

1. 全量内联 SVG 经 `rsvg-convert` 生成原尺寸 PNG，并测可见 bbox/留白；
2. Word/WPS PDF（或通过文字保真校验的 LibreOffice fallback）经 Poppler 逐页转 PNG；
3. 生成 SVG 与 DOCX 页面 contact sheets（只作索引）；
4. 生成 `visual-review-<sha>-prepare.template.json`，绑定 candidate、DOCX、PNG 与 manifest hash。

### 3. 派独立视觉 reviewer

读取并严格执行 `references/visual-review-protocol.md`。用 fresh-context Subagent/视觉 Agent 分批审查；不要让作者逐图人工兜底，也不要让生产者自审。writing-reviewer 的文字 finding 可以作为线索，但只有符合 JSON 协议且覆盖全部 artifact 的独立审查才是 gate 证据。

把各 reviewer 的 JSON 放入独立目录，例如：

```text
.book-gate-evidence/reviews-current/
├── reviewer-a.json
├── reviewer-b.json
└── reviewer-c.json
```

### 4. 验证最终 release

```bash
python3 "$GATE" verify "$ROOT" \
  --requirements "$REQ" \
  --stage release \
  --docx /path/to/final.docx \
  --pdf /path/to/word-or-wps-export.pdf \
  --producer-id <worker-or-branch-id> \
  --visual-review "$OUT/reviews-current" \
  --out "$OUT"
```

只有退出码 `0` 且 `overall=RELEASE_VERIFIED` 才能把对应候选标为 release 完成。DOCX/正文/SVG/规则/模板任一变动都会改变 hash，旧 review 自动失效。

### 5. 检查证据是否陈旧

```bash
python3 "$GATE" status "$OUT/evidence-<sha>-release.json" \
  --project-root "$ROOT" --requirements "$REQ"
```

输出 `STALE` 时必须重跑，不得继续引用旧的“通过”结论。

## Requirement 配置

复制 `requirements.yaml` 到书籍项目，命名为 `book-gate.yaml`，只在项目文件中维护项目阈值与权威规范指针。不要把同一条写作规则复制进 Skill；配置只记录 rule id、verifier、阈值、scope 与 canonical source。

每条 requirement 必须包含：

- `id`、`stage`、`scope`、`verifier`、`threshold`
- `blocking`（YAML bool）
- `needs_human_review`（YAML bool）

无自动 verifier 的规则必须显式 `needs_human_review: true`，这会阻断 gate，直到实现机器检查或由结构化独立审查接管。

## 回归规则

每个作者发现的真实逃逸都先变成故障注入测试，再修 verifier。运行：

```bash
python3 -m unittest discover -s /path/to/book-gate/scripts -p 'test_*.py' -v
```

至少保留 Mermaid、空规则绿灯、中文 ASCII 引号、脚注星号、相邻图无承接、SVG 渲染/留白、旧 hash、自审、漏图和 DOCX 图片数不足等样本。一个抓不住已知错误的 verifier 不具备放行资格。

## 边界

- 本技能做最终成品 acceptance，不替代写作、配图生成或 writing-reviewer 的内容审查。
- 本技能不决定作者主观取舍；主观项由独立视觉 reviewer 按项目已有规范判定并写结构化证据。
- `prepare` 只生成审查包，不等于通过；`release` 才是最终门禁。
- evidence 含本地渲染件与上下文片段，应保持在项目忽略目录，不提交含客户信息的证据包。
