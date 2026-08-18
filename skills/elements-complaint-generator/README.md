# elements-complaint-generator · 要素式起诉状生成器

把律师已写好的**常规起诉状**（Markdown / docx / 对话口述）转换为符合最高法**法〔2025〕82 号**《部分案件起诉状、答辩状示范文本》（2025-07-14 全国推广）格式的**要素式 Word 文书**——格式像素级保真，可直接提交法院立案。

## 快速使用

```bash
# 三段式：① 案由匹配 → ② Agent 抽要素（用户复核）→ ③ 渲染 docx
python scripts/fill_template.py \
  --case-type 09-private-lending \     # 或 05-divorce / 06-sale / 60-enforcement / 两位编号
  --elements 案件/elements.json \
  --output 案件/要素式起诉状.docx

# 批量模式（金融机构批量场景）
python scripts/fill_template.py --batch 目录/ --output 目录/
```

## 覆盖范围

| 层级 | 案由数 | 说明 |
|---|---|---|
| **精调级** | **26** | 上册 01-21 全覆盖（离婚/买卖/金融借款/民间借贷/信用卡/房屋买卖/租赁/融资租赁/建工/物业/劳动/证券/保险×4/交通）+ 中册知产 22-30 全覆盖 + 60 强制执行 |
| 通用级 | 42 | 当事人（自然人+法人）+ 标题填空 + 唯一标签 + 调解 + 具状 + **通用勾选** + 多当事人扩容 |
| 不做 | 45 | 答辩状 / 第三人意见陈述书（定位聚焦起诉状） |

模板源：法〔2025〕82 号完整版 113 棵 OOXML 源码树（上 42 + 中 28 + 下 43），git 可 diff。

## 技术架构

```
普通起诉状 → [Agent 按 Schema 抽要素] → elements.json（人复核）
          → [纯代码 lxml <w:t> 跨 run 替换] → 保真 docx
```

- **Agent 负责抽取**（语义理解）：按三层 reference（通用层/路由层/案由层）产出 elements.json
- **纯代码负责填充**（确定性）：lxml 编辑 OOXML XML 树，跨 run 精确替换，不破坏字体/表格/勾选框
- **格式铁律**：只替换文字内容，不改段落/表格/回车结构——"连回车都复刻"

## 三层 Reference

| 层 | 文档 | 用途 |
|---|---|---|
| 通用层 | `references/common-elements.md` | 当事人/代理人/调解意愿/落款跨案由定义 |
| 路由层 | `references/case-routing.md` | 113 棵树索引（案由/册/key/支持状态/关键词） |
| 案由层 | `references/case-types/NN-*.md` + `skeletons/` | 精调定稿 + 通用级骨架 |

## 回归保障

`bash tests/run_e2e.sh` — 27 产物带标签断言 + 哨兵（双日/双勾/标签吃字）+ 68 树冒烟全绿。

## 依赖

- Python 3.11+ / lxml（唯一硬依赖）
- LibreOffice（仅模板入库时 OLE2→docx 转换）

## License

CC-BY-NC · [杨卫薪律师](https://github.com/cat-xierluo/legal-skills)
