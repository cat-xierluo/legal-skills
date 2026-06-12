# 模板目录指南

`templates/` 只存放可直接在 draw.io / diagrams.net 打开的 `.drawio` 模板。说明性 Markdown、XML 语法教程和开发规则统一放在 `references/`，避免模板目录混杂。

## 目录结构

```text
templates/
├── litigation/                 # 诉讼、仲裁、执行、程序推进
├── corporate/                  # 公司治理、股权、交易架构
├── compliance/                 # 合规治理、审批矩阵、风险地图
├── contract/                   # 合同审查、合同履约、合同流程
├── intellectual-property/      # 知识产权侵权、权利要求、权属对比
├── real-estate/                # 房地产项目、空间标注、项目平面
└── service/                    # 法律服务方案、客户汇报、交付边界
```

## 模板文件

| 路径 | 用途 |
|------|------|
| `templates/litigation/multi-party-relation.drawio` | 多主体关系图 |
| `templates/litigation/layered-timeline.drawio` | 分层程序时间轴 |
| `templates/litigation/litigation-route.drawio` | 案件办理路线图 |
| `templates/litigation/three-line-flow.drawio` | 票据/资金/合同三线流向图 |
| `templates/litigation/unified-entry-flow.drawio` | 统一入口流程图 |
| `templates/litigation/issue-evidence-matrix.drawio` | 争点-证据矩阵 |
| `templates/litigation/system-path-comparison.drawio` | 制度路径对比图 |
| `templates/litigation/construction-delay-progress.drawio` | 工期延误进度图 |
| `templates/corporate/equity-structure.drawio` | 股权结构图 |
| `templates/corporate/transaction-architecture.drawio` | 交易架构图 |
| `templates/corporate/equity-change-before-after.drawio` | 股权变动前后对比图 |
| `templates/compliance/compliance-risk-map.drawio` | 合规风险地图 |
| `templates/compliance/approval-matrix.drawio` | 审批矩阵 |
| `templates/contract/contract-review-swim.drawio` | 合同审查泳道图 |
| `templates/intellectual-property/infringement-compare.drawio` | 侵权对比图 |
| `templates/real-estate/project-site-map.drawio` | 项目平面标注图 |
| `templates/service/service-roadmap.drawio` | 法律服务路线图 |
| `templates/service/scope-deliverable-matrix.drawio` | 范围-交付物矩阵 |

## XML 示例

以下文件是 XML 写法示例，不是可直接打开的 `.drawio` 模板：

| 文件 | 用途 |
|------|------|
| `references/xml-example-litigation-flow.md` | 流程图 XML 示例 |
| `references/xml-example-evidence-chain.md` | 证据链图 XML 示例 |
| `references/xml-example-contract-structure.md` | 合同结构图 XML 示例 |
| `references/xml-example-case-timeline.md` | 时间轴 XML 示例 |
| `references/xml-example-infringement-map.md` | 对比图 XML 示例 |
| `references/xml-example-claim-breakdown.md` | 分解图 XML 示例 |

## 工具入口

- XML 自检：`python scripts/validate_drawio.py templates/litigation/litigation-route.drawio`
- 批量导出：`python scripts/export_drawio.py templates/ --recursive`，输出目录会同时包含 `.drawio`、`.svg` 和 `.png`
- 高清 PNG：`python scripts/export_drawio.py templates/litigation/litigation-route.drawio --format png --png-scale 3`
- 命名规范检查：`python scripts/normalize_naming.py templates/litigation/litigation-route.drawio`

## 新模板规则

新增 `.drawio` 模板时：

1. 使用英文目录名和英文文件名。
2. 按业务条线放入现有目录；确需新增目录时使用小写英文和连字符。
3. 在 `.drawio` 文件顶部 XML 注释中写明：适用场景 ID、必要输入字段、默认布局、可变参数。
4. 同步更新 `references/chart-decision-tree.md` 和本文件的模板列表。
5. 运行 XML 自检、命名规范检查和一次导出抽检。
