# 本地配置（profile）

slides 的生成与导出默认**不需要任何配置**即可使用：没有配置时按匿名安全默认值工作，产出的课件只包含本次内容，不含任何讲者姓名、联系方式、头像或二维码。

讲者身份、联系方式、品牌与展示开关都放在**技能目录之外**的本地配置里，由每位使用者自己初始化。技能更新或重装不会覆盖它。

## 1. 配置解析顺序

一次运行**只加载一个配置文件**，不会把不同层的姓名、单位和二维码拼在一起。命中即停止：

| 顺序 | 位置 | 用途 |
|---|---|---|
| 1 | `--config <路径>` 或环境变量 `SLIDES_PROFILE` | 显式指定，优先级最高 |
| 2 | 从工作目录向上查找 `.slides/profile.json` | 单个课件项目的配置 |
| 3 | `<技能目录>/config/profile.local.json` | 便携安装（发布时必须排除） |
| 4 | `$SLIDES_HOME/profile.local.json`，默认 `~/.config/slides/profile.local.json` | 常规个人配置（推荐） |
| 5 | 无 | 匿名默认值 |

约束：

- **相对路径统一相对于被选配置文件所在目录解析**，不按当前工作目录猜。允许写显式本机绝对路径，但绝对路径不得进入公开模板。
- 显式指定的路径不存在、或 JSON 损坏时**直接报错**，不会悄悄回退到另一份资料。
- 缺失的键用匿名默认值补齐（空字符串 / `false` / 空数组），只补结构，不引入任何身份信息。

## 2. 字段

完整定义见 [profile.schema.json](../config/profile.schema.json)，可直接复制的空白模板见 [profile.example.json](../config/profile.example.json)。

| 段 | 字段 | 说明 |
|---|---|---|
| `identity` | `name` / `titles[]` / `organization` / `bio` | 讲者身份。留空即省略，不虚构。 |
| `contact` | `wechat` / `email` / `website` | 联系方式，属个人资料，不进公开包。 |
| `assets` | `avatar` / `logo` / `wechat_qr` / `public_account_qr` / `footprint_photos[]` | 私有素材路径。是否读取由 `presentation.show_*` 决定。 |
| `brand` | `style` / `custom_style_file` / `footer_text` / `footer_style` | 默认风格与页脚。留空即中性默认。 |
| `presentation` | `locale` / `aspect_ratio` / `font_families[]` / `show_profile` / `show_footprints` / `show_wechat_qr` / `show_public_account_qr` / `intro_pages` / `closing_mode` | 表现参数与展示开关。 |
| `sources` | `bio_file` / `footprints_file` | 权威来源**指针**，只作核对入口，不内联内容；数字不核实不补写。 |
| `preferences_file` | 路径 | 个人写作与排版补充（自由文本资料，不提供执行入口）。 |

`presentation.intro_pages` 取 `0` / `2` / `3`：`0` 不生成介绍页，`2` 为「身份 + 现场」两页，`3` 为「身份 + 路径总览 + 现场」三页。
`presentation.closing_mode` 取 `summary`（总结金句，可配二维码）/ `thanks` / `none`。

## 3. 展示开关与素材读取

`show_* = false` 时**不读取**对应图片与来源文件（不是「读了不显示」）：

| 素材 / 来源 | 控制开关 |
|---|---|
| `assets.avatar`、`assets.logo`、`sources.bio_file` | `show_profile` |
| `assets.wechat_qr` | `show_wechat_qr` |
| `assets.public_account_qr` | `show_public_account_qr` |
| `assets.footprint_photos`、`sources.footprints_file` | `show_footprints` |

缺项处理：

- 二维码是「明确要求展示」的承诺——**启用但未配置路径会判定为错误**，阻塞校验；明确要求必须包含二维码的交付不得用旧码或假码顶替。
- 头像、Logo、现场照片与来源指针缺失只提示：生成时省略该元素并重排页面，不虚构内容。

`false`、空字符串、空数组都是**有效覆盖**，不会被低层默认值补回——所以关闭某一项后，页面上不会残留占位框或空图。

## 4. 初始化

```bash
# 引导模式：打印需要向使用者收集的字段清单（供 Agent 逐项询问）
node scripts/init-profile.js

# 非交互回填
node scripts/init-profile.js \
  --name "张三" --title 律师 --organization "某某律师事务所" \
  --wechat-qr ~/assets/wx.png --show-wechat-qr \
  --footer-text "张三 律师 · 某某律师事务所" \
  --style 商务权威

# 整份导入（也接受 load-profile.js --json 的输出）
node scripts/init-profile.js --from-json ./my-profile.json
```

- 默认写入 `~/.config/slides/profile.local.json`；`--dir` 改目录，`--skill-local` 写技能目录（便携安装用），`--out` 指定文件。
- 目标已存在时**拒绝覆盖**，必须显式加 `--force`。
- 初始化**不扫描全盘**寻找微信、头像、通讯录或历史课件；路径由使用者给出。

校验：

```bash
node scripts/check-profile.js
node scripts/check-profile.js --config ~/.config/slides/profile.local.json
```

`check-profile.js` 只输出字段是否已填、开关状态和路径状态，不打印姓名、微信、简介等资料值；存在错误时退出码非零。

生成流程与 `convert.js` 读取同一份解析结果：

```bash
node scripts/load-profile.js            # 来源、开关、已启用素材（不含资料值）
node scripts/load-profile.js --json     # 完整配置 JSON，供生成流程消费
node scripts/load-profile.js --field identity.name
node scripts/load-profile.js --footer   # 仅页脚文本
```

## 5. 资源策略：本地创作 vs 课件交付

- **本地创作**：HTML 直接引用配置中的私有素材路径，维持单一来源，不复制。
- **发给他人的课件**：需要另做资源整理——把本次明确启用的头像 / Logo / 二维码 / 字体复制进该课件的资源目录、把引用改为相对路径，并实际移动目录后打开验证。单 HTML 内嵌与 PPTX 本地图片限制分别处理，不为「单文件」一概内嵌 base64。字体能否分发须核来源许可。**当前无专用打包脚本**：按上述步骤手工完成，并在交付前逐项核对「启用项都在、关闭项都没带上」。
- **技能发布包**与**课件资源包**分开构建：后者按需包含讲者信息，前者不含任何真实个人资料。把二维码路径写进 config **不等于**图片已脱离发布范围。

## 6. 从旧版个人资料迁移（原使用者）

早期版本把讲者身份、品牌与素材路径写在技能目录内（如 `references/` 下的个人信息文件与个人风格 JSON）。这些文件**不再是运行配置**，应迁出技能目录：

1. 清点并**备份**旧个人信息文件、个人品牌指南/风格与其素材引用，记录来源，不移动素材库原件。
2. 转成自己的 `profile.local.json` 与私有偏好文件，继续指向既有素材库路径；履历只留权威来源指针，避免另养一套会变的数字。
3. 个人风格 JSON 移到配置目录的 `styles/`，并在 `brand.custom_style_file` 指向它；可复用的中性视觉参数（配色、字号、间距）可另存为内置中性预设。
4. 需要身份页与二维码的，在 `presentation.*` 中显式置 `true` 并配置对应路径；不需要则保持关闭。
5. 用同一份合成课件跑迁移前后对照，核身份字段、风格、页脚、图片与二维码解码结果，通过后再切换。
6. 旧私有资料保留为恢复来源（放在 `config/local/`，被 `.gitignore` 忽略），运行时不读取、不进发布包，不作为新使用者的回退。目录约定：`assets/` 是常规素材目录（图片默认忽略）；私有配置用 `.local` 后缀放在 `config/` 常规位置（如 `config/profile.local.json`、个人风格 `config/xxx.local.json`）。

## 7. 发布边界

- 公私区分的总约定：**Git 跟踪的 = 可发布通用内容；被 `.gitignore` 忽略的 = 使用者私有**（`.gitignore` 随包分发，使用者装包后同样受其保护）。`.gitignore` 只防新增跟踪；发布打包另用明确允许清单，不依赖 ignore 规则兜底。
- 不进公开包：`config/*.local.*`（私有配置/风格/偏好）、`config/local/`（旧版原件）、`assets/` 内图片等二进制（默认私有，公开素材用 `!` 显式豁免）、真实头像 / 二维码 / 照片、运行产物。
- 保留：通用引擎与模板、公开风格库、schema 与空白模板、初始化 / 校验 / 解析工具、去个人化的说明文档。
- 技能作者署名与 LICENSE 中的版权信息属发布元数据，与「生成课件的讲者身份」分开，去个人化时不删必要署名。
- 发布打包过**「具体名称门禁」**（`scripts/check-privacy.js`，随包分发）：通用模式检测，不依赖任何私有名单——具体机构名（地名+机构后缀）、人名+职称、绝对机路径、内部编号/memo、联系方式、个人素材文件名、真实课程路径，以及日期与项目语境、来源标签与版本/页码的组合标识；**配置文件从严**（config/ 与 profile 类文件的身份、联系、素材字段必须为空模板）。有意保留的作者署名通过 INTENTIONAL 登记表豁免（逐条 file+正则+理由，可审计）。门禁不过则拒绝打包。

- 运行 `node scripts/pack-public.js --list` 核对公开清单，或 `--out <新的 zip 路径>` / `--out-dir <新的目录路径>` 生成包；输出必须在技能目录外且不存在；ZIP 打包使用 Python 3 标准库，以正确记录中文文件名编码。打包器同时核对相对 Markdown 链接，拒绝符号链接，并复扫实际暂存字节。
- 模式扫描不识别所有简称、跨段组合或图片内文字。发布前仍须人工复核纳入文件与素材；发现具体来源时保留技术经验、泛化识别信息，不通过扩大署名豁免绕过检查。

### 维护者回归

在 `scripts/` 运行 `npm run test:privacy`、`npm run test:publication`、`npm run test:conversion`。隐私回归只需 Node.js；打包回归还需 Python 3 校验 ZIP 中文文件名；转换回归需要已安装的 npm 依赖和 Playwright Chromium，以及 Python 3（检查 PPTX ZIP/XML）、Poppler 的 `pdfinfo`（检查 PDF 页数）。这些额外工具仅用于维护者回归，不是日常转换依赖。PDF 专项回归为 `node tests/test-html2pdf-fidelity.mjs`。
