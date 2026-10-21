# assets/ — 素材目录

slides 的常规素材目录：头像、二维码、Logo、现场照片、字体等生成课件要引用的素材文件。

## 公私规则

- **图片与二进制默认私有**：`assets/*.png`、`*.jpg` 等由 `.gitignore` 默认忽略——个人照片和二维码正是最容易误入版本库/发布包的内容，默认拦住最安全。
- **要公开分发的素材用 `!` 显式豁免**：在 `.gitignore` 加一行 `!assets/共享图标.png`，并确认它在 `pack-public.js` 的允许清单里。
- **文本素材**（SVG、说明文件）默认可以跟踪，入发布包前仍过 `check-privacy.js` 门禁。

## 引用方式

在 `config/profile.local.json` 里以相对路径引用（相对 `config/` 目录）：

```json
"assets": {
  "avatar": "../assets/avatar.png",
  "wechat_qr": "../assets/wechat-qr.jpg"
}
```

本地创作时 HTML 直接引用这里的绝对/相对路径，单一来源不复制；**发给他人的课件**按
[configuration.md](../references/configuration.md) §5 做资源整理（复制进课件目录、改相对引用、移动后验证）。
