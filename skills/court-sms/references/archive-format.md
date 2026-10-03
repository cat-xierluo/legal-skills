# 内部归档格式

每次处理一条短信后，在 `archive/` 下创建一条 JSON 记录，不保存文书本身（文书归档到案件目录）。

## 文件路径

`archive/YYYYMMDD_HHMMSS_{案号后4位}.json`

## JSON 结构

```json
{
  "id": "20260404_143025_1234",
  "timestamp": "2026-04-04T14:30:25+08:00",
  "sms_raw": "【xx市人民法院】张三，您好！您有（2025）苏0981民初1234号案件文书送达，请点击链接查收：https://zxfw.court.gov.cn/...",
  "parsed": {
    "type": "document_delivery",
    "case_number": "（2025）苏0981民初1234号",
    "parties": ["张三", "xx有限公司"],
    "court": "xx市人民法院"
  },
  "download": {
    "source_url": "https://zxfw.court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?qdbh=XX&sdbh=XX&sdsin=XX",
    "params": { "qdbh": "XX", "sdbh": "XX", "sdsin": "XX" },
    "method": "curl",
    "status": "success",
    "document_title": "受理通知书",
    "api_response": {
      "c_fymc": "苏州工业园区人民法院",
      "c_fybh": "1275",
      "documents": [
        {
          "c_wsmc": "传票（东沙湖法庭）",
          "c_wsbh": "ecb8fe64e4834804b50ea0f9257327e0"
        }
      ]
    }
  },
  "document": {
    "type": "一审判决书",
    "sent_at": "2026-04-08T10:00:00+08:00",
    "sent_at_source": "短信网关时间（仅发送线索）",
    "received_at": "2026-04-08T14:30:00+08:00",
    "document_id": "DEMO-DOC",
    "recipient_id": "DEMO-RECIPIENT",
    "service": {"status": "pending", "served_on": null, "evidence_refs": [], "reason": "未取得该文书送达凭证"},
    "deadline_status": "pending",
    "deadline_basis": null,
    "appeal_deadline": null,
    "appeal_days_remaining": null
  },
  "archive": {
    "matched_case": "260101 张三与李四合同纠纷",
    "target_path": "260101 张三与李四合同纠纷/受理通知书（张三与李四合同纠纷）_20260404收.pdf",
    "summary": "传票：2025年4月15日 14:30 第3法庭开庭"
  }
}
```

## 字段说明

| 字段 | 必需 | 说明 |
|------|------|------|
| `id` | 是 | 归档唯一标识，即文件名（不含扩展名） |
| `timestamp` | 是 | ISO 8601 格式的处理时间 |
| `sms_raw` | 是 | 短信原文，完整保留 |
| `parsed.type` | 是 | 短信类型：`document_delivery` / `filing_notification` / `info_notification` |
| `parsed.case_number` | 否 | 提取到的案号，未提取到时为 `null` |
| `parsed.parties` | 否 | 提取到的当事人列表 |
| `parsed.court` | 否 | 提取到的法院名称 |
| `parsed.sent_at` | 否 | 法院发送时间，从短信或送达平台提取 |
| `parsed.received_at` | 否 | 用户收到时间（如有） |
| `download.source_url` | 否 | 原始下载链接 |
| `download.params` | 否 | 从 URL 提取的参数（如 qdbh/sdbh/sdsin） |
| `download.method` | 否 | 实际使用的下载方式：`curl` / `cli` / `mcp` / `manual` / `null`（无下载链接） |
| `download.status` | 是 | 下载状态：`success` / `failed` / `manual` / `skipped` |
| `download.api_response` | 否 | API 完整响应，包含 c_fymc（法院名称）、c_fybh（法院编号）、documents 数组（每份文书详情）。实测 zxfw `getWsListBySdbhNew` 响应**不含** `dt_cjsj`，送达时间须另寻来源（见 `document.sent_at_source`） |
| `download.api_response.c_fymc` | 否 | 法院名称（来自 API） |
| `download.api_response.c_fybh` | 否 | 法院编号 |
| `download.api_response.documents[].c_wsmc` | 否 | 文书名称 |
| `download.api_response.documents[].c_wsbh` | 否 | 文书编号（UUID） |
| `document.type` | 否 | 文书类型：判决书/裁定书/调解书等（从 PDF 解析） |
| `document.sent_at` | 否 | 仅指实际发送事件时间，未知为 null；不作为法律送达日起算字段 |
| `document.sent_at_source` | 否 | 发送事件来源，不等于送达证明；二维码/落款时间另存 time_clues，不能填入 sent_at |
| `document.received_at` | 否 | 用户收到时间（手机短信网关时间） |
| `document.appeal_deadline` | 否 | 仅 deadline_status=confirmed 时填写；否则 null |
| `document.appeal_days_remaining` | 否 | 仅 confirmed 时填写；按办案适用本地日期计算，其他状态为 null |
| `archive.matched_case` | 否 | 匹配到的案件目录名 |
| `archive.target_path` | 否 | 文书最终归档的相对路径 |

## v1.5.3 送达与期限字段

按 [送达与期限规则](service-and-deadlines.md) 核对证据，证据检查输入单独保存于私有本地文件。

| 字段 | 说明 |
|------|------|
| `document.document_id` / `recipient_id` | 文书和受送达人的稳定标识；不得将整批默认绑定到同一人 |
| `document.time_clues` | 二维码生成、签发、下载等线索数组，含类型、时间和原件定位；不能直接推定送达 |
| `document.service` | 检查器输出：status、served_on（YYYY-MM-DD）、evidence_refs、reason |
| `document.deadline_status` | pending / confirmed / not_applicable；缺省按 pending |
| `document.deadline_basis` | 救济告知定位、适用法条、期间日数、日历来源、核对日期和受送达人；不以类型表替代 |

多份文书/多个受送达人使用 `documents[]` 分别保存上述单文书结构；旧 `document` 仅用于一个文书/受送达人组合，不同时维护两套互相矛盾的结果。未知送达不阻碍归档，必须显式保留待核验提醒。

旧记录没有 service 时不得默认 confirmed；再次处理时保留旧值的更正历史，撤下未核实的当前期限/倒计时。只更新本次授权范围内的档案，不批量改写其他案件。
