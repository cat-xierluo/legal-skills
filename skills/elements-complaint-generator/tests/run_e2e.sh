#!/usr/bin/env bash
# elements-complaint-generator 端到端回归用例
# 跑完整链路：md → extract → fill → 校验
set -e
SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SKILL_DIR"

echo "[e2e] Step 1/4: 抽取 md → elements.json"
python3 -B scripts/extract_from_markdown.py \
  --case-type 02-private-lending \
  --input tests/fixtures/02-private-lending-complaint.md \
  --output tests/output/02-private-lending-elements.json 2>&1 | tail -3

echo "[e2e] Step 2/4: 渲染 elements.json → docx"
python3 -B scripts/fill_template.py \
  --case-type 02-private-lending \
  --elements tests/output/02-private-lending-elements.json \
  --output tests/output/02-private-lending-e2e.docx 2>&1 | tail -3

echo "[e2e] Step 3/4: 校验输出 docx（python-docx 可读 + 关键字段齐全）"
python3 - <<'PYEOF'
import sys
from docx import Document
d = Document("tests/output/02-private-lending-e2e.docx")
hits = sum(p.text.count("☑") for p in d.paragraphs)
for t in d.tables:
    for row in t.rows:
        for cell in row.cells:
            for p in cell.paragraphs:
                hits += p.text.count("☑")
texts = []
for p in d.paragraphs: texts.append(p.text)
for t in d.tables:
    for row in t.rows:
        for cell in row.cells:
            for p in cell.paragraphs:
                texts.append(p.text)
full = "\n".join(texts)
print(f"[e2e] ☑ = {hits}")
checks = ["张三", "李四", "110105850312001", "310105900725001", "12300000001", "500000", "汉族"]
missing = [k for k in checks if k not in full]
if missing:
    print(f"[e2e] ✗ 缺失字段: {missing}")
    sys.exit(1)
print("[e2e] ✓ 关键字段全部到位")
PYEOF

echo "[e2e] Step 4/4: 同时跑 sample fixture（手工构造的全要素）"
python3 -B scripts/fill_template.py \
  --case-type 02-private-lending \
  --elements tests/fixtures/02-private-lending-sample.json \
  --output tests/output/02-private-lending-sample-filled.docx 2>&1 | tail -3

echo
echo "[e2e] 端到端通过。产物："
echo "  tests/output/02-private-lending-e2e.docx         (md → 渲染)"
echo "  tests/output/02-private-lending-sample-filled.docx (sample → 渲染)"