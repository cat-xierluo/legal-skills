# 通义听悟内部 REST API 参考

> 通过逆向分析 `tingwu.aliyun.com` 网页端 JavaScript 和网络请求获取。

## 基础信息

- **Base URL**: `https://tingwu.aliyun.com/api`
- **认证方式**: Cookie（`.aliyun.com` 域名，约 22 个 cookie）
- **通用请求头**:
  ```
  x-b3-traceid: <UUID>        # 随机 UUID
  x-b3-sampled: 1
  x-tw-canary:                # 空值
  Content-Type: application/json
  ```

## 完整转录流程（6 步）

### Step 1: `generatePutLink` — 获取上传凭证

```
POST /api/trans/request?generatePutLink
```

**请求体**:
```json
{
  "action": "generatePutLink",
  "version": "1.0",
  "taskId": "<唯一文件ID>",
  "useSts": 1,
  "fileSize": 36212345,
  "dirId": 0,
  "fileContentType": "audio/mpeg",
  "tag": {
    "showName": "文件名",
    "fileFormat": "mp3",
    "fileType": "local",
    "lang": "cn",
    "roleSplitNum": 4,
    "translateSwitch": false,
    "transTargetValue": "",
    "originalFlag": 0
  }
}
```

**响应**:
```json
{
  "code": "0",
  "data": {
    "transId": "4l6xqal2bdkanm2y",
    "putLink": "https://...",
    "getLink": "https://...",
    "sts": {
      "endpoint": "https://oss-cn-shanghai.aliyuncs.com",
      "accessKeyId": "STS.xxx",
      "accessKeySecret": "xxx",
      "securityToken": "xxx",
      "bucket": "prod-new-tingwu-saas-xxx",
      "fileKey": "tingwu/prod/xxx",
      "sldEnabled": false
    }
  }
}
```

### Step 2: OSS STS 上传

使用 `oss2` SDK:

```python
import oss2

auth = oss2.StsAuth(accessKeyId, accessKeySecret, securityToken)
bucket = oss2.Bucket(auth, endpoint, bucket_name)
bucket.put_object_from_file(fileKey, local_file_path)
# 大文件可用 oss2.resumable_upload() 分片上传
```

### Step 3: `syncPutLink` — 确认上传完成

```
POST /api/trans/request?syncPutLink
```

**请求体**:
```json
{
  "action": "syncPutLink",
  "version": "1.0",
  "fileLink": "<putLink URL>",
  "fileSize": 36212345,
  "transId": "4l6xqal2bdkanm2y",
  "duration": 123
}
```

### Step 4: `startTrans` — 启动转录任务

```
POST /api/trans/request?startTrans
```

**请求体**:
```json
{
  "action": "startTrans",
  "version": "1.0",
  "userId": "",
  "transIds": ["4l6xqal2bdkanm2y"],
  "tag": {
    "lang": "cn",
    "roleSplitNum": 4
  }
}
```

### Step 5: `getTransList` — 轮询任务状态

```
POST /api/trans/request?getTransList
```

**请求体**:
```json
{
  "action": "getTransList",
  "version": "1.0",
  "userId": "",
  "filter": {"status": [1, 2, 3, 4, 11]},
  "preview": 1,
  "pageNo": 1,
  "pageSize": 1000
}
```

**状态码**: 1=排队, 2=转录中, 3=已完成, 4=失败, 11=上传中

### Step 6: `getTransResult` — 获取转录结果

```
POST /api/trans/getTransResult?c=web
```

**请求体**:
```json
{
  "action": "getTransResult",
  "version": "1.0",
  "transId": "4l6xqal2bdkanm2y"
}
```

**响应关键字段**:
- `duration`: 总时长（秒）
- `wordCount`: 总字数
- `status`: 0=已完成
- `result`: JSON 字符串，解析后为分页结构

**`result` 数据结构**:
```json
{
  "0": [
    {
      "pi": "1775191379502500000",
      "sc": [
        {
          "bt": 62400,
          "et": 62811,
          "id": 10,
          "si": 1,
          "tc": "这会儿"
        }
      ]
    }
  ]
}
```

字段说明:
- `bt` / `et`: 开始/结束时间（毫秒）
- `si`: 说话人 ID
- `tc`: 文本内容
- `pi`: 段落 ID

## 辅助 API

| 端点 | 用途 |
|------|------|
| `GET /api/account/v2/user/info?c=web` | 验证登录状态 |
| `GET /api/tingwu/account/info?c=web` | 账户配额信息 |
| `POST /api/trans/request?delTrans` | 删除转录记录 |

## 参数说明

### 语言 (`lang`)
| 值 | 说明 |
|----|------|
| `cn` | 中文（默认） |
| `en` | 英文 |
| `ja` | 日文 |
| `cant` | 粤语 |
| `cn_en` | 中英混合 |

### 说话人 (`roleSplitNum`)
| 值 | 说明 |
|----|------|
| `0` | 不区分 |
| `1` | 单人 |
| `2` | 两人 |
| `4` | 多人（默认） |

### 文件格式
支持: mp3, wav, m4a, wma, aac, ogg, amr, flac, aiff, mp4, wmv, mov, mkv, webm, avi 等

### 文件限制
- 音频最大 500MB
- 视频最大 6GB
- 单文件最长 6 小时
