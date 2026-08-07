# 智合法律研究 API 参考文档

## 基础信息

| 项目 | 值 |
|------|-----|
| 基础 URL | `https://fc-openresearch-qzquocekez.cn-shanghai.fcapp.run` |
| 认证方式 | Bearer Token (JWT) |
| Token 有效期 | 72 小时 |
| Content-Type | `application/json` |

---

## 认证接口

### 1. 发送验证码

**请求**
```http
POST /api/auth/send-code
Content-Type: application/json

{
  "phone": "13800138000"
}
```

**响应**
```json
{
  "code": 200,
  "message": "验证码已发送",
  "data": {
    "masked_phone": "138****8000"
  }
}
```

**错误码**
| 状态码 | 说明 |
|--------|------|
| 400 | 手机号格式错误 |
| 429 | 验证码发送过于频繁 |

---

### 2. 验证登录

**请求**
```http
POST /api/auth/verify-code
Content-Type: application/json

{
  "phone": "13800138000",
  "code": "123456"
}
```

**响应**
```json
{
  "code": 200,
  "message": "登录成功",
  "data": {
    "token": "eyJhbGciOiJIUzI1NiIs...",
    "is_vip": true,
    "vip_type": "豪华版",
    "expire_at": "2026-03-13T14:30:00Z"
  }
}
```

**错误码**
| 状态码 | 说明 |
|--------|------|
| 400 | 验证码错误或已过期 |
| 404 | 用户不存在 |

---

## 用户接口

### 3. 获取用户信息

**请求**
```http
GET /api/user/profile
Authorization: Bearer <token>
```

**响应**
```json
{
  "code": 200,
  "data": {
    "phone": "138****8000",
    "is_vip": true,
    "vip_type": "豪华版",
    "vip_expire_at": "2026-12-31T23:59:59Z"
  }
}
```

**错误码**
| 状态码 | 说明 |
|--------|------|
| 401 | Token 无效或已过期 |

---

## 研究接口

### 4. 提交研究问题

**请求**
```http
POST /api/research/query
Authorization: Bearer <token>
Content-Type: application/json

{
  "query": "劳动合同到期不续签需要赔偿吗？"
}
```

**响应**
```json
{
  "code": 200,
  "message": "已提交，正在进行法律调研分析",
  "data": {
    "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "estimated_completion": "14:35:30",
    "estimated_seconds": 210
  }
}
```

**错误码**
| 状态码 | 说明 |
|--------|------|
| 401 | 未认证 |
| 403 | 非会员 |
| 429 | 频率限制（每分钟1次，或已有任务进行中） |

---

### 5. 查询任务状态

**请求**
```http
GET /api/research/status/<task_id>
Authorization: Bearer <token>
```

**响应**
```json
{
  "code": 200,
  "data": {
    "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "status": "completed",
    "progress": 100,
    "has_report": true,
    "created_at": "2026-03-10T14:30:00Z",
    "completed_at": "2026-03-10T14:34:30Z"
  }
}
```

**状态值**
| 状态 | 说明 |
|------|------|
| `pending` | 排队中 |
| `running` | 处理中 |
| `completed` | 已完成 |
| `failed` | 失败 |
| `timeout` | 超时 |

---

### 6. 获取研究结果

**请求**
```http
GET /api/research/result/<task_id>
Authorization: Bearer <token>
```

**响应**
```json
{
  "code": 200,
  "data": {
    "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "query": "劳动合同到期不续签需要赔偿吗？",
    "text_result": "根据《劳动合同法》第四十六条...",
    "created_at": "2026-03-10T14:34:30Z"
  }
}
```

---

### 7. 获取报告下载链接

**请求**
```http
GET /api/research/report/<task_id>
Authorization: Bearer <token>
```

**响应**
```json
{
  "code": 200,
  "data": {
    "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "has_report": true,
    "report_url": "https://storage.example.com/reports/xxx.docx?sign=...",
    "filename": "法律研究报告_20260310_143430.docx",
    "expires_at": "2026-03-17T14:34:30Z"
  }
}
```

**注意**：报告链接有效期 7 天，过期后重新调用接口会自动刷新签名。

---

### 8. 查看历史任务

**请求**
```http
GET /api/research/history?page=1&size=10
Authorization: Bearer <token>
```

**响应**
```json
{
  "code": 200,
  "data": {
    "total": 25,
    "page": 1,
    "size": 10,
    "tasks": [
      {
        "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "query": "劳动合同到期不续签需要赔偿吗？",
        "status": "completed",
        "has_report": true,
        "created_at": "2026-03-10T14:30:00Z"
      }
    ]
  }
}
```

---

## 错误处理

### 通用错误响应格式

```json
{
  "code": 400,
  "message": "错误描述",
  "data": null
}
```

### HTTP 状态码对照

| HTTP 状态码 | 含义 | 处理建议 |
|-------------|------|----------|
| 200 | 成功 | - |
| 400 | 参数错误 | 检查请求参数格式 |
| 401 | 未认证/Token过期 | 重新登录 |
| 403 | 非会员/无权限 | 引导开通会员 |
| 404 | 资源不存在 | 检查 task_id 或通过 history 查询 |
| 429 | 频率限制 | 稍后重试 |
| 502 | 上游服务错误 | 稍后重试 |

---

## 限流规则

| 接口 | 限制 |
|------|------|
| 发送验证码 | 每手机号 1次/分钟 |
| 提交研究问题 | 每用户 1次/分钟，同时只能有1个进行中任务 |
| 其他接口 | 无特殊限制 |

---

## 调试技巧

### 使用 curl 测试

```bash
# 设置 Token
export TOKEN="your_token_here"

# 检查登录状态
curl -s -X GET "https://fc-openresearch-qzquocekez.cn-shanghai.fcapp.run/api/user/profile" \
  -H "Authorization: Bearer $TOKEN" | jq

# 提交问题
curl -s -X POST "https://fc-openresearch-qzquocekez.cn-shanghai.fcapp.run/api/research/query" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "测试问题"}' | jq
```

### 使用脚本工具

```bash
# 使用封装好的脚本
./scripts/auth.sh check
./scripts/research.sh submit "测试问题"
./scripts/research.sh status <task_id>
```
