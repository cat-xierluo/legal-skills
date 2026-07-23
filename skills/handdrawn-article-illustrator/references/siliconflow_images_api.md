# SiliconFlow Images API 要点

## Endpoint

- `POST https://api.siliconflow.cn/v1/images/generations`

## 鉴权

- Header：`Authorization: Bearer <AK>`
- AK 获取：`https://cloud.siliconflow.cn/account/ak`
- 本 Skill 默认不读取 AK；只有批量入口显式传入 `--allow-api` 并选择 `t2i`、`edit` 或 `guided-edit` 时才使用。

## 关键字段

- `model`：默认推荐 `Tongyi-MAI/Z-Image-Turbo`；对照模型可用 `Qwen/Qwen-Image`，编辑 fallback 可用 `Qwen/Qwen-Image-Edit-2509`
- `prompt`
- `negative_prompt`
- `image`：编辑模式使用，支持 base64 data URL 或公网 URL
- `image2` / `image3`：可选风格参考图
- `image_size`：默认 `auto`；Z-Image 使用 `2048x872`，Qwen t2i 使用 `1664x928`
- `cfg`：SiliconFlow t2i 可用，建议 3-5 起步

## 限制

- 生成结果 URL 有效期短，应立即下载保存。
- `Qwen/Qwen-Image-Edit-2509` 不支持 `image_size`，需要用底图锁定比例。
- 公众号首图默认生成 `2048x872` 后导出 `2400x1024`；显式使用 Qwen t2i 时再用 `1664x928`。
