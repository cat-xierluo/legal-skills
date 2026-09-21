# 法律材料与证据处理专家套件

> [下载完整专家套件](https://github.com/cat-xierluo/legal-skills/releases/latest/download/suite-legal-material-evidence-0.1.0.zip)

把法院文书、扫描件、PDF、图片、录音、视频和会议记录整理成可归档、可检索、可继续分析的数字化材料。

## 适用场景

- 收案后批量整理客户提交的纸质或电子材料；
- 对扫描 PDF、图片证据、录音录像、法院短信和会议记录做结构化处理；
- 在进入案件分析或文书起草前，建立可追溯的材料底座。

## 不适用场景

- 不替代证据真实性、合法性、关联性判断；
- 不自动形成诉讼策略或法律结论；
- 不保证第三方 OCR、听写或法院链接服务始终可用。

## 包含的 Skills

| Skill | 在本套件中的作用 | 单独下载 |
| :--- | :--- | :--- |
| [legal-ocr](../../skills/legal-ocr/) | 统一路由 PDF、图片、Office 和网页内容识别 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/legal-ocr-1.6.0.zip) |
| [pdf-processor](../../skills/pdf-processor/) | 预处理、OCR 双层化、合并、页码和压缩 PDF | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/pdf-processor-2.13.0.zip) |
| [pdf-organizer](../../skills/pdf-organizer/) | 建立页面索引并按内容拆分、合并和规范命名 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/pdf-organizer-0.6.0.zip) |
| [video-screenshot](../../skills/video-screenshot/) | 从录屏或视频中筛选关键帧和证据线索 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/video-screenshot-0.8.2.zip) |
| [funasr-transcribe](../../skills/funasr-transcribe/) | 本地转录音视频并保留时间戳 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/funasr-transcribe-1.9.4.zip) |
| [transcription-corrector](../../skills/transcription-corrector/) | 纠正同音字、专有名词和 ASR 漂移 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/transcription-corrector-1.0.8.zip) |
| [tingwu-asr](../../skills/tingwu-asr/) | 使用通义听悟完成云端长音视频转录 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/tingwu-asr-0.4.6.zip) |
| [court-sms](../../skills/court-sms/) | 解析法院短信、下载文书并归档到案件目录 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/court-sms-1.5.1.zip) |
| [dingtalk-minutes](../../skills/dingtalk-minutes/) | 读取钉钉 AI 听记摘要、逐字稿和待办 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/dingtalk-minutes-1.1.0.zip) |

## 建议使用方式

1. 先用 `court-sms`、`dingtalk-minutes` 或转录 Skill 取得原始内容；
2. 用 `legal-ocr` 路由文档识别，必要时交给 `pdf-processor` 做双层化和预处理；
3. 用 `pdf-organizer` 建立页级索引、拆分和命名；
4. 视频类材料用 `video-screenshot` 提取关键帧，转录稿再用 `transcription-corrector` 纠错；
5. 人工核对页码、时间戳、原件对应关系和识别错误后，再交给分析类 Skill。

## 安装方法

1. 下载并解压完整套件 ZIP；
2. 阅读各成员 `SKILL.md` 的依赖和凭证说明；
3. 把解压目录中的 `skills/*` 复制到所用 Agent 的 Skills 根目录；
4. 重新加载 Agent，让各 Skill 按自己的 `description` 正常触发。

也可以只下载上表中的单个 Skill。仓库里的 `skills/` 是符号链接集合，Release ZIP 中会展开为真实目录。

## 人工复核与使用边界

OCR 和语音识别结果必须与原件抽样核对。涉及证据提交、期限、案号、当事人身份或保密材料时，应由承办律师确认；下载或转录外部材料前，应确保具有合法权限并遵循最小必要原则。

## 版本与许可证

当前套件版本为 `0.1.0`。套件外层文件按 [LICENSE.txt](LICENSE.txt) 的 MIT License 授权；各成员 Skill 按其目录内 `LICENSE.txt` 分别授权。下载或使用套件不改变成员原有许可条件。
