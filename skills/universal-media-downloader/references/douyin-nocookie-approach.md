# 抖音无登录下载思路（video_id + aweme.snssdk.com 直连法）

> 2026-08-02 实测可用 · 麻辣小龙侠 🦭
> 视频样本: `https://v.douyin.com/aAQgycBvBp0/`（鱼亦乐作品，94s，5MB）

---

## 一句话

抖音短链 → SSR share 页面提 `video_id` → `aweme.snssdk.com/v1/play` 接口拿 302 CDN 直链 → curl 带 referer 下载。**全程不需要 cookie / 登录态 / 签名。**

---

## 背景：为什么需要这条思路

### MEMORY 旧结论（2026-07-14，**已部分修正**）

> "无登录下载抖音"在当前反爬下不成立。
> F2 业务层硬校验 cookie 非空 + 拖音 API 强制 `a_bogus` 签名（来自 msToken，msToken 来自登录态）。
> **没 cookie = 没合法签名 = API 拒绝。**

### 2026-08-02 实测发现

`a_bogus` / msToken 签名墙**只覆盖部分 API**——`aweme.snssdk.com/aweme/v1/play/` 这个**旧版直链接口**对仅带 `video_id` 的请求仍返回 302，无需签名。这就是突破口。

---

## 三种路径的撞墙记录（实测顺序）

### 路径 ①：yt-dlp（**失败**）

```bash
yt-dlp "https://v.douyin.com/aAQgycBvBp0/"
```

**报错**：
```
[Douyin] 7665930064613199114: Failed to parse JSON
ERROR: Fresh cookies (not necessarily logged in) are needed
```

**原因**：yt-dlp 的 Douyin extractor 走 `www.douyin.com/web/api/v2/aweme/post/` 类接口，这些接口要 `s_v_web_id` cookie + `a_bogus` 签名。没 cookie 直接 412 / 空 JSON。

### 路径 ②：iesdouyin iteminfo API（**失败**）

```bash
curl "https://www.iesdouyin.com/web/api/v2/aweme/iteminfo/?item_ids=7665930064613199114"
```

**返回**：
```json
{"status_code":11110,"status_msg":"encrypt_data_miss"}
```

**原因**：旧版 iteminfo 接口已加加密拦截，返回 `encrypt_data_miss` 不再吐 JSON 明文。

### 路径 ③：SSR share 页 + aweme.snssdk.com 直连（**成功 ✅**）

这是本文档的核心思路。下面详述。

---

## 核心实现（路径 ③ 详解）

### Step 1：解析短链拿 video_id

抖音短链 `v.douyin.com/XXX` 会 302 重定向到 `www.douyin.com/video/<numeric_id>`。但 numeric_id 不是我们要的——需要的是 SSR share 页里那个 `v0d00fg10000...` 格式的 `uri`。

```bash
VID_NUMERIC="7665930064613199114"

# 拉 SSR share 页（iPhone UA）
curl -sL -A "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15" \
  "https://www.iesdouyin.com/share/video/${VID_NUMERIC}/" \
  | grep -oE '"uri":"v0[0-9a-f]+"'
```

**输出**：
```
"uri":"v0d00fg10000d9hd4fvog65hpvajlnp0"
```

这个 `v0d00fg10000d9hd4fvog65hpvajlnp0` 就是 `video_id`（也叫 `uri`），是后续直连接口的钥匙。

### Step 2：用 video_id 换 302 CDN 直链

```bash
VIDEO_ID="v0d00fg10000d9hd4fvog65hpvajlnp0"

curl -sLI -A "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15" \
  "https://aweme.snssdk.com/aweme/v1/play/?video_id=${VIDEO_ID}&ratio=540p&line=0"
```

**关键响应**：
```
HTTP/2 302
location: https://v95-hzyy-thr-daily-colda.douyinvod.com/412fa6dcedda.../video/tos/cn/tos-cn-ve-15/.../?a=1128&br=433&bt=433&mime_type=video_mp4&...
HTTP/2 200
```

**为什么这一步能过签名墙**：
- `aweme.snssdk.com` 是**App 端旧域名**（区别于 `www.douyin.com` 的 Web 端）
- `/aweme/v1/play/` 是**直链播放接口**，设计目的就是给播放器喂视频流，不承担反爬职责
- 它只校验 `video_id` 合法性 + 时间戳过期，**不需要 `a_bogus` / msToken**
- `ratio=540p` 控制清晰度，可选 `540p / 720p / 1080p`（540p 是 SSR share 页默认档）

### Step 3：下载直链（带 referer）

```bash
PLAY_URL="https://v95-hzyy-thr-daily-colda.douyinvod.com/..."  # Step 2 拿到的完整 location

curl -L \
  -A "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15" \
  -e "https://www.douyin.com/" \
  -o "鱼亦乐_7665930064613199114.mp4" \
  "$PLAY_URL"
```

**为什么需要 `-e "https://www.douyin.com/"`**：抖音 CDN 校验 referer，空 referer 会 403。带上 douyin.com 域名 referer 才放行。

---

## 一键脚本（可直接复制用）

```bash
#!/usr/bin/env bash
# 抖音无登录下载（短链 → video_id → 直连）
# 用法: ./douyin-dl.sh "https://v.douyin.com/XXXXX/" [输出文件名]

set -euo pipefail
SHARE_URL="${1:?用法: $0 <短链或 share URL> [输出名]}"
OUT_NAME="${2:-douyin_$(date +%s)}.mp4"
UA="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"

# 1. 短链 → numeric_id
NUMERIC=$(curl -sLI -A "$UA" "$SHARE_URL" 2>&1 \
  | awk -F'/video/' '/location.*douyin.com\/video\//{split($2,a,"?");print a[1]}' \
  | tail -1)
[ -z "$NUMERIC" ] && { echo "❌ 无法解析短链"; exit 1; }
echo "📌 numeric_id: $NUMERIC"

# 2. SSR share 页 → video_id (uri)
VIDEO_ID=$(curl -sL -A "$UA" "https://www.iesdouyin.com/share/video/${NUMERIC}/" \
  | grep -oE '"uri":"v0[0-9a-f]+"' | head -1 | cut -d'"' -f4)
[ -z "$VIDEO_ID" ] && { echo "❌ 无法提取 video_id"; exit 1; }
echo "📌 video_id:   $VIDEO_ID"

# 3. video_id → 302 CDN 直链
PLAY_URL=$(curl -sLI -A "$UA" \
  "https://aweme.snssdk.com/aweme/v1/play/?video_id=${VIDEO_ID}&ratio=540p&line=0" 2>&1 \
  | awk -F': ' 'tolower($1)=="location"{sub(/\r$/,"",$2);print $2}' | tail -1)
[ -z "$PLAY_URL" ] && { echo "❌ 未拿到 CDN 直链"; exit 1; }
echo "📡 CDN 直链长度: ${#PLAY_URL}"

# 4. 下载
echo "⬇️  下载中 → $OUT_NAME"
curl -L -A "$UA" -e "https://www.douyin.com/" -o "$OUT_NAME" "$PLAY_URL"

# 5. 验证
echo ""
echo "✅ 完成: $(ls -lh "$OUT_NAME" | awk '{print $5, $9}')"
ffprobe -v error -show_entries format=duration,size,bit_rate \
  -of default=noprint_wrappers=1 "$OUT_NAME" 2>/dev/null || true
```

---

## 边界与已知限制

| 情况 | 表现 | 说明 |
|---|---|---|
| 公开视频 | ✅ 可下 | 本文方法 |
| 私密 / 仅好友可见 | ❌ 拿不到 video_id | SSR share 页不渲染 play_addr |
| 已删除 / 异地限制 | ❌ numeric_id 解析失败 | 短链 302 到 404 页 |
| 直播 / 直播回放 | ❌ 不适用 | 走的是 live 接口，不是 v1/play |
| 图文笔记（非视频） | ⚠️ 拿到的是首图 | v1/play 只返回视频流 |
| ratio=1080p | ⚠️ 部分老视频没 1080 源 | 会 fallback 到 540p |

**直链有效期**：约 1-2 小时（CDN 时间戳签名过期），过期后需重新走 Step 2 拿新链接。

---

## 与 MEMORY 旧教训的关系

MEMORY 2026-07-14 那条"无登录下载抖音不成立"**结论方向对、但覆盖面过宽**：

- ✅ 仍然成立：`www.douyin.com/web/api/v2/aweme/post/` 类**业务 API** 确实要签名（F2 / yt-dlp 走的全是这条）
- ❌ 已修正：`aweme.snssdk.com/aweme/v1/play/` **播放直链接口**不要签名，只要 video_id

下次写 MEMORY 时应改成：**"抖音业务 API（详情/列表/评论）需要 a_bogus 签名墙，但播放直链接口 aweme.snssdk.com/v1/play 仍开放 video_id 直连。yt-dlp 撞签名墙时走 video_id → v1/play → CDN 302 这条路径。"**

---

## 关键域名速查

| 域名 | 用途 | 是否要签名 |
|---|---|---|
| `v.douyin.com` | 短链 | 无（302 重定向） |
| `www.douyin.com/video/<numeric_id>` | Web 端视频页 | Web cookie（反爬严） |
| `www.iesdouyin.com/share/video/<numeric_id>/` | SSR share 页 | 无（渲染 HTML 暴露 video_id） |
| `www.iesdouyin.com/web/api/v2/aweme/iteminfo/` | 旧版详情 API | ❌ 已加 `encrypt_data_miss` |
| `aweme.snssdk.com/aweme/v1/play/?video_id=<>` | **播放直链 API** | **无**（只要 video_id） |
| `*.douyinvod.com` | CDN 视频流 | 只要 referer 合法 |

---

## 反爬演进预判

这条路径能跑，本质是抖音**新旧 API 并存**的窗口期：

- 旧 `aweme.snssdk.com/v1/play` 给 App 老客户端向后兼容，暂时没下掉签名校验
- 新 `www.douyin.com/web/api/v2/aweme/*` 全上 `a_bogus` + msToken 签名

**预判**：抖音迟早会把旧 API 也纳入签名墙（或强制走新域名）。届时本方法失效，需要找下一个未覆盖的接口。监控信号：

1. `aweme.snssdk.com/v1/play` 开始返回 412 / 空 body / `status_code > 0`
2. SSR share 页不再渲染 `play_addr.uri` 字段
3. yt-dlp 更新 Douyin extractor 后突然能跑（说明找到新绕过路径）

---

*文档结束 · 麻辣小龙侠 🦭 · 2026-08-02*
