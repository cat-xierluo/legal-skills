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
      "dt_cjsj": "2026-03-18T07:44:00.000+00:00",
      "documents": [
        {
          "c_wsmc": "传票（东沙湖法庭）",
          "c_wsbh": "ecb8fe64e4834804b50ea0f9257327e0",
          "dt_cjsj": "2026-03-18T07:44:00.000+00:00"
        }
      ]
    }
  },
  "document": {
    "type": "一审判决书",
    "sent_at": "2026-04-08T10:00:00+08:00",
    "received_at": "2026-04-08T14:30:00+08:00",
    "appeal_deadline": "2026-04-23T23:59:59+08:00",
    "appeal_days_remaining": 15
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
| `download.api_response` | 否 | API 完整响应，包含 c_fymc（法院名称）、c_fybh（法院编号）、dt_cjsj（送达时间）、documents 数组（每份文书详情） |
| `download.api_response.c_fymc` | 否 | 法院名称（来自 API） |
| `download.api_response.c_fybh` | 否 | 法院编号 |
| `download.api_response.dt_cjsj` | 否 | 送达记录创建时间（ISO 8601），作为 sent_at 来源 |
| `download.api_response.documents[].c_wsmc` | 否 | 文书名称 |
| `download.api_response.documents[].c_wsbh` | 否 | 文书编号（UUID） |
| `download.api_response.documents[].dt_cjsj` | 否 | 单份文书的送达时间 |
| `document.type` | 否 | 文书类型：判决书/裁定书/调解书等（从 PDF 解析） |
| `document.sent_at` | 否 | 法院发送时间（送达平台记录） |
| `document.received_at` | 否 | 用户收到时间（手机短信网关时间） |
| `document.appeal_deadline` | 否 | 上诉截止日期（根据案件类型计算） |
| `document.appeal_days_remaining` | 否 | 剩余上诉天数 |
| `archive.matched_case` | 否 | 匹配到的案件目录名 |
| `archive.target_path` | 否 | 文书最终归档的相对路径 |
