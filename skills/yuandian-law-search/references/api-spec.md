# yd_law_search 接口文档

元典法条检索技能 `yd_law_search`。

---

## 1. 法条语义检索（`POST /search`）

### 接口地址
- 默认基础地址：`http://aiapi.ailaw.cn:8319`
- 路径：`/search`

### 调用方式
`POST /search?api_key={api_key}`

### 示例
```bash
curl -X POST 'http://aiapi.ailaw.cn:8319/search?api_key=${YD_API_KEY}' \
  -H 'Content-Type: application/json' \
  --data-raw '{
    "query":"正当防卫的限度",
    "effect1":["法律"],
    "sxx":["现行有效"]
  }'
```

### 参数说明

#### Query 参数
| 参数 | 必填 | 说明 |
|------|------|------|
| api_key | 是 | 调用密钥，可通过 https://passport.legalmind.cn/apiKey/manage 获取 |

#### Body 参数（JSON）
| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| query | string | 是 | - | 用户输入问题 |
| effect1 | string[] | 否 | `[]` | 效力级别筛选，可选值：宪法、法律、司法解释、行政法规、监察法规、部门规章、党内法规、军事法规规章、立法机关工作文件、行政机关工作文件、行业/团体规范、地方性法规、自治条例和单行条例、地方司法文件、地方政府规章、地方规范性文件、地方律协规定|
| sxx | string[] | 否 | `[]` | 时效性筛选,可选值：现行有效、失效、已被修改、部分失效、尚未生效 |


### 返回结果
成功时：
```json
{
  "code": 200,
  "message": "成功",
  "data": [
    {
      "法条全文": "...",
      "法规名称": "...",
      "法条序号": "...",
      "发布机关": "...",
      "发文字号": "...",
      "发布日期": "...",
      "实施日期": "...",
      "时效性": "...",
      "法规链接": "https://ydzk.chineselaw.com/..."
    }
  ]
}
```
---

## 2. 法条关键词检索（`POST /search_keyword`）

### 接口地址
- 默认基础地址：`http://aiapi.ailaw.cn:8319`
- 路径：`/search_keyword`

### 调用方式
`POST /search_keyword?api_key={api_key}`

### 示例
```bash
curl -X POST 'http://aiapi.ailaw.cn:8319/search_keyword?api_key=${YD_API_KEY}' \
  -H 'Content-Type: application/json' \
  --data-raw '{
    "query":"人工智能 监管",
    "effect1":["法律"],
    "sxx":["现行有效"],
    "fbrq_start": "2022-01-01",
    "fbrq_end": "2026-03-01",
    "ssrq_start": "2022-01-01",
    "ssrq_end": "2026-01-01"
  }'
```

### 参数说明

#### Query 参数
| 参数 | 必填 | 说明 |
|------|------|------|
| api_key | 是 | 调用密钥，可通过 https://passport.legalmind.cn/apiKey/manage 获取 |

#### Body 参数（JSON）
| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| query | string | 是 | - | 关键词 |
| effect1 | string[] | 否 | `[]` | 效力级别筛选，可选值：宪法、法律、司法解释、行政法规、监察法规、部门规章、党内法规、军事法规规章、立法机关工作文件、行政机关工作文件、行业/团体规范、地方性法规、自治条例和单行条例、地方司法文件、地方政府规章、地方规范性文件、地方律协规定|
| sxx | string[] | 否 | `[]` | 时效性筛选，可选值：现行有效、失效、已被修改、部分失效、尚未生效 |
| search_mode | string | 否 | `and` | 控制多关键词之间的检索逻辑关系，可选值： `and` 或 `or` |
| fbrq_start | string | 否 | 空 | 发布日期区间起点，格式 `yyyy-MM-dd`；筛选规则为日期 **大于等于** `fbrq_start` 且 **小于等于** `fbrq_end`（闭区间，两端均含） |
| fbrq_end | string | 否 | 空 | 发布日期区间终点，格式同上 |
| ssrq_start | string | 否 | 空 | 实施日期区间起点，格式与规则同上 |
| ssrq_end | string | 否 | 空 | 实施日期区间终点，格式同上 |

### 返回结果
成功时：
```json
{
  "code": 200,
  "message": "成功",
  "data": [
    {
      "法条全文": "...",
      "法规名称": "...",
      "法条序号": "...",
      "发布机关": "...",
      "发文字号": "...",
      "发布日期": "...",
      "实施日期": "...",
      "时效性": "...",
      "法规链接": "https://ydzk.chineselaw.com/..."
    }
  ]
}
```


---

## 3. 法条详情检索（`POST /search_ft_info`）

### 接口地址
- 默认基础地址：`http://aiapi.ailaw.cn:8319`
- 路径：`/search_ft_info`

### 调用方式
`POST /search_ft_info?api_key={api_key}`

### 示例
```bash
curl -X POST 'http://aiapi.ailaw.cn:8319/search_ft_info?api_key=${YD_API_KEY}' \
  -H 'Content-Type: application/json' \
  --data-raw '{
    "query":"民法典",
    "ft_name":"第十五条"
  }'
```

### 参数说明

#### Query 参数
| 参数 | 必填 | 说明 |
|------|------|------|
| api_key | 是 | 调用密钥，可通过 https://passport.legalmind.cn/apiKey/manage 获取 |

#### Body 参数（JSON）
| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| query | string | 是 | - | 传法规名称（law_name） |
| ft_name | string | 是 | - | 法条编号（ft_name），如：`第十五条` / `2` |
| reference_date | string | 否 | 空 | 参考日期，格式 `yyyy-MM-dd`|


### 返回结果
成功时：
```json
{
  "code": 200,
  "message": "成功",
  "data": [
    {
      "法条全文": "...",
      "法规名称": "...",
      "法条序号": "...",
      "发布机关": "...",
      "发文字号": "...",
      "发布日期": "...",
      "实施日期": "...",
      "时效性": "...",
      "法规链接": "https://ydzk.chineselaw.com/..."
    }
  ]
}
```

---

## 4. 案例关键词检索（`POST /search_al`）


### 接口地址
- 默认基础地址：`http://aiapi.ailaw.cn:8319`
- 路径：`/search_al`

### 调用方式
`POST /search_al?api_key={api_key}`

### 示例
```bash
curl -X POST 'http://aiapi.ailaw.cn:8319/search_al?api_key=${YD_API_KEY}' \
  -H 'Content-Type: application/json' \
  --data-raw '{
    "query": "人工智能",
    "search_mode": "and",
    "authority_only": false
  }'
```

仅检索权威案例库时，将 `authority_only` 设为 `true`。

### 参数说明

#### Query 参数
| 参数 | 必填 | 说明 |
|------|------|------|
| api_key | 是 | 调用密钥，可通过 https://passport.legalmind.cn/apiKey/manage 获取 |

#### Body 参数（JSON）

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| authority_only | boolean | 否 | `false` | `false` 或未传：同时检索**普通案例**与**权威案例**（结果合并去重）；`true`：仅检索**权威案例**。`authority_only`  |
| query | string | 否 | 空 | 全文关键词，多个关键词半角空格分隔 |
| search_mode | string | 否 | `and` | 多关键词逻辑：`and` / `or` |
| ah | string | 否 | 空 | 案号 |
| title | string | 否 | 空 | 标题 |
| ay | string[] | 否 | `[]` | 案由/罪名，多值为或关系 |
| jbdw | string[] | 否 | `[]` | 经办法院，多值为或关系 |
| ajlb | string | 否 | 空 | 案件类别，可选值：刑事案件、民事案件、行政案件、执行案件、管辖案件、国家赔偿与司法救助案件、强制清算与破产案件、国际司法协助案件、非诉保全审查案件、其他案件 |
| xzqh_p | string[] | 否 | `[]` | 行政区划省，可选值：北京、天津、河北、山西、内蒙古、辽宁、吉林、黑龙江、上海、江苏、浙江、安徽、福建、江西、山东、河南、湖北、湖南、广东、广西、海南、重庆、四川、贵州、云南、西藏、陕西、甘肃、青海、宁夏、新疆、最高、新疆生产建设兵团；多值为或关系 |
| wszl | string[] | 否 | `[]` | 文书种类，可选值：判决书、裁定书、调解书、决定书；多值为或关系 |
| jarq_start | string | 否 | 空 | 结案/案件日期区间起点，`yyyy-MM-dd` |
| jarq_end | string | 否 | 空 | 结案/案件日期区间终点，`yyyy-MM-dd` |


### 返回结果

```json
{
  "code": 200,
  "message": "成功",
  "data": [
    {
      "案号": "（2025）桂09民终192号",
      "类型": "典型案例",
      "标题": "...",
      "正文": "...",
      "案例链接": "https://ydzk.chineselaw.com/ydzk/caseDetail/...",
      "案件类别": "民事案件",
      "案由": ["买卖合同纠纷"],
      "文书种类": "判决书",
      "经办法院": "玉林市中级人民法院",
      "行政区划省": "广西",
      "行政区划市": "玉林市",
      "裁判日期": "2025-04-17"
    }
  ]
}
```

---

## 5. 案例向量检索（`POST /search_al_vector`）


### 接口地址
- 默认基础地址：`http://aiapi.ailaw.cn:8319`
- 路径：`/search_al_vector`

### 调用方式
`POST /search_al_vector?api_key={api_key}`

### 示例
```bash
curl -X POST 'http://aiapi.ailaw.cn:8319/search_al_vector?api_key=${YD_API_KEY}' \
  -H 'Content-Type: application/json' \
  --data-raw '{
    "query": "正当防卫的限度",
    "jarq_start": "2020-01-01",
    "jarq_end": "2025-12-31",
    "authority_only": false,
    "xzqh_p": "广西"
  }'
```

### 参数说明

#### Query 参数
| 参数 | 必填 | 说明 |
|------|------|------|
| api_key | 是 | 调用密钥，可通过 https://passport.legalmind.cn/apiKey/manage 获取 |

#### Body 参数（JSON）

**检索主参数**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| query | string | 是 | 用户问题/检索语句 |


**案例过滤**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| jarq_start | string | 否 | 案件日期过滤起点，`YYYY-MM-DD` |
| jarq_end | string | 否 | 案件日期过滤终点，格式同上 |
| fayuan | string[] | 否 | 法院名称列表 |
| authority_only | boolean | 否 | `true` 时仅检索权威/典型案例库|
| xzqh_p | string | 否 | 行政区划省，可选值：北京、天津、河北、山西、内蒙古、辽宁、吉林、黑龙江、上海、江苏、浙江、安徽、福建、江西、山东、河南、湖北、湖南、广东、广西、海南、重庆、四川、贵州、云南、西藏、陕西、甘肃、青海、宁夏、新疆、最高、新疆生产建设兵团 |
| wenshu_type | string | 否 | 案件类型，如：刑事案件、民事案件、行政案件 |
| wszl | string[] | 否 | 文书种类，可选值：判决书、裁定书、调解书、决定书；多值为或关系|

### 返回结果

```json
{
  "code": 200,
  "message": "成功",
  "data": [
    {
      "案号": "（2025）桂09民终192号",
      "类型": "普通案例",
      "标题": "...",
      "正文": "...",
      "案例链接": "https://ydzk.chineselaw.com/ydzk/caseDetail/case/...",
      "案件类别": "民事案件",
      "案由": ["买卖合同纠纷"],
      "文书种类": "判决书",
      "经办法院": "玉林市中级人民法院",
      "行政区划省": "广西",
      "行政区划市": "玉林市",
      "裁判日期": "2025-04-17"
    }
  ]
}
```