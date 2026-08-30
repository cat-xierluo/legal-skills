# 变更日志

## [0.5.0] - 2026-08-30

### 新增

- **抖音三级自动 fallback（游客 cookie 环）**：`download_media.py` 在抖音域名 + 用户未显式传 cookie 且 yt-dlp 失败时，继「无登录直连」后新增最后一环——自动依次从本机 `chrome`、`safari` 读一份**游客 cookie**（访问 cookie，无需登录抖音）重跑 yt-dlp，即可过 `Fresh cookies are needed` 校验。浏览器读取失败自动换下一个，全失败回显原始报错；`--audio-only` 同样适用此环
- 用户显式传 `--cookies` / `--cookies-from-browser` 时均不触发自动 fallback（尊重用户选择）

### 背景（实测记录）

- 2026-08-30 实测：SSR share 页已对无 cookie 请求停止渲染 `play_addr.uri`（返回 `video_layout:null` 壳页 + 风控标记），v0.3.0 无登录直连路径卡在上游提不到 video_id（监控信号 #2 命中）；游客 cookie 通道实测成功（6.2MB / 140s / ffprobe 通过）

### 改进

- `download_media.py`：`SAVED_FILEPATH` 解析逻辑提取为 `emit_saved_path()`（主路径与 fallback 重试路径复用，消除重复）
- SKILL.md frontmatter `version` 由滞留的 0.2.0 同步至 0.5.0；抖音小节改写为三级 fallback 说明
- `references/douyin-nocookie-approach.md` 追加 2026-08-30 补记：失效现场、游客 cookie 原理与边界

## [0.4.0] - 2026-08-03

### 改进

- **默认下载目录改为 `~/Downloads/`**（取消自包含）：产物不再存入 skill 内部 `downloads/`，改为用户主目录 `~/Downloads/`，方便日常访问。见 DECISIONS.md DEC-004（取代 DEC-002）
- `download_media.py`: `DEFAULT_OUT_DIR` 由 `SCRIPT_DIR / "downloads"` 改为 `Path.home() / "Downloads"`
- SKILL.md「默认保存目录」说明同步更新

### 注意

- 此变更不向后迁移历史文件；skill 内 `downloads/` 目录若存在则保留但不再写入
- 仍可用 `--out-dir` 自定义任意路径

## [0.3.0] - 2026-08-02

### 新增

- 抖音视频无登录下载 fallback：新增 `scripts/download_douyin_video_nocookie.py`，基于 `aweme.snssdk.com/aweme/v1/play/` 直连接口（仅需 video_id，不需要 cookie / a_bogus 签名）
- `download_media.py` 在「抖音域名 + 未传 cookies + 非纯音频」且 yt-dlp 失败时，自动调用上述脚本兜底，对用户无感
- 归档原理依据到 `references/douyin-nocookie-approach.md`（含反爬演进预判与失效监控信号）
- 下载支持 aria2c 多线程加速（16 连接 + 断点续传，自动检测；未安装则回退 requests 单线程）
- `download_media.py` 新增 `--cookies-from-browser` 参数（chrome/firefox/safari/edge），直接读浏览器登录态，免手动导 cookies.txt；与 `--cookies` 互斥

### 修复

- 修正 video_id 提取正则：uri 实际含 g/h/i 等非 hex 字符，照搬文档的 `v0[0-9a-f]+` 会在结尾 `"` 断言处失配，改为锚定 `play_addr` 的精确正则 + 宽字符兜底

### 验证

- 样本 `https://v.douyin.com/aAQgycBvBp0/` 端到端通过：4.97 MB / 94.02s / ffprobe 校验通过；yt-dlp 2026.06.09 撞签名墙（`Fresh cookies are needed`）后自动 fallback 成功

## [0.2.0] - 2026-02-12

### 新增

- 新增字幕下载支持（`--subtitles` 参数）
- 支持指定字幕语言（`--sub-lang`，默认下载所有可用字幕）
- 添加"依赖"章节到 SKILL.md

### 改进

- 修复 docstring 中的过时路径示例

## [0.1.0] - 2026-02-12

### 新增

- 初始版本，基于 yt-dlp 实现通用视频/播客下载功能
- 支持抖音、B站、YouTube 等主流视频平台
- 支持小宇宙等播客平台音频下载
- 支持音频-only 模式（MP3 等格式）
- 支持 cookies.txt 用于绕过登录/403限制
- 支持代理设置
- 自包含 downloads/ 输出目录

### 技术优化

- 默认输出目录设置为技能目录下的 `downloads/` 文件夹
- 使用 `--print after_move:filepath` 获取最终文件路径
- 输出 `SAVED_FILEPATH` 便于 AI 解析结果

### 待办事项

- 添加更多平台兼容性测试
- 添加批量下载支持（播放列表）
