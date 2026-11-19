# chat-html 抽取规则

**版本**: v0.16.1

## 适用输入

- Cubox Pro 导出的笔记 HTML（含 `<div class="reader-page">` 包装）
- 微信 PC 端导出的聊天记录 HTML（页面内含 `chatlog` 标记）
- 微信 Mac 端导出的 JSON（与 HTML 一组）

不适用：`<iframe>` 嵌入 PDF、加密 IM 包、bAK/.dat 二进制。

## 三类资源白名单

| 类别 | 命中模式 |
|------|---------|
| 外链下载 | `<a href="...">下载</a>` 且 href 命中下表域名 |
| 图片 | `<img src>` 含 `cubox.pro/images/`、`images.weserv.nl` 或 base64 内嵌 |
| 视频 | `<video src>`、`<source src>` 命中 mp4/mov/m4v/mkv/webm 后缀 |

### 外链域名白名单

| 域名 | 备注 |
|------|------|
| `cubox.pro` | Cubox Pro 下载文件 |
| `files.cubox.pro` | 同上 |
| `images.cubox.pro` | 图床 |
| `weixin.qq.com` | 微信文件 |
| `szfiles.wx.qq.com` | 微信文件 |
| `wenshu.court.gov.cn` | 文书网（少见） |
| `*.aliyundrive.com` | 阿里云盘（如出现） |
| `*.weiyun.com` | 微云 |
| `pan.baidu.com` | 百度网盘 |

## 输出

- 抽到的资源候选写入聊天 HTML 主记录的 `extra_json.chat_html.resources`
- 本次抽取不伪造独立 `materials` 记录；下载成功的文件在下一次扫描时按真实文件入库并建立来源说明
- 下载到源目录 `外部资源/{YYYY-MM-DD}_{原文件名}` 子目录
- 失败与下载到 0 字节也记入 manifest（`download_status` 字段在 `extra_json.chat_html`）

默认只做识别与 dry-run。只有用户核对域名、数量和下载目录后，才使用 `--chat-html-download`。

## 下载安全边界

- 只接受公网 HTTP/HTTPS URL 或受限的 `data:image`；拒绝 `file://`、localhost、私网字面地址和其他协议。
- 白名单按解析后的主机名精确匹配或子域匹配，确保 `files.cubox.pro.evil.example` 不命中。
- 主机名必须先完成 DNS 解析，且全部解析结果都必须是公网地址；解析到私网、回环、保留地址时直接拒绝，防止白名单域名被 DNS 指向内网造成绕过。
- 重定向目标继续执行公网 URL 校验与 DNS 公网校验，解析失败按可重试错误处理，解析到非公网地址按永久拒绝处理。
- 单个资源最大 100MB；超限、空响应、401/403 和网络失败写入 manifest，不中断其他条目。
- 同名文件追加 `_2`、`_3`，不要覆盖既有文件。

### 文件命名边界

- 发送日期能从该资源附近文字抽出：使用 `{YYYY-MM-DD}_{原文件名}`
- 抽不出：使用 `待识别日期_{原文件名}` 并在 manifest `extra_json.chat_html.resources[i].context` 留痕
- 同日文件名冲突：自动追加 `_2`、`_3`... 直到不冲突（不覆盖已有文件）

## 必选清单对账

在材料清单尾部追加"外部资源抽取对账"小节：

| 类别 | 应抽取 | 实际抽取 | 命中规则 |
| --- | --- | --- | --- |
| 外链下载 | N1 | n1 | <a href> + 域名白名单 |
| 图片 | N2 | n2 | <img> + cubox images 或 base64 |
| 视频 | N3 | n3 | <video>/<source> + 视频后缀 |
| 合计 | N | n | — |
