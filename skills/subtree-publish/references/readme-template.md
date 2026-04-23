# <skill-name>

<一句话说明：这个 skill 帮谁、在什么场景下、产出什么。>

> <一句话价值主张：让访客在 30 秒内知道为什么值得安装。>

<!--
README.md 面向独立 GitHub 仓库的人类访客，不是 skill runtime 文件。
Release zip / 安装包中仍应排除 README.md，避免污染实际 skill 目录。

个性化信息来源：
- 优先读取 config/readme-profile.json（本地配置，不提交）
- 可用 SUBTREE_README_* 环境变量临时覆盖
- 公开发布只保留 config/readme-profile.example.json 作为字段示例

写作原则：
- outcome first：首屏先讲结果，不先讲 YAML/frontmatter/目录结构
- example first：前半部分给真实用户提问和 AI 介入方式
- install executable：安装步骤必须能照做；有依赖就就近写命令
- boundary clear：适合/不适合分开写，高风险场景必须写清免责声明
- trust supported：复杂 skill 补方法框架、覆盖范围、质量支撑和关键文件
- metadata consistent：许可证、作者、项目链接必须与 SKILL.md / LICENSE.txt 一致

复杂度 profile：
- minimal：保留“典型场景 / 能产出什么 / 安装方式 / 使用边界 / 许可证 / 作者 / 关联项目”
- standard：再加“适合谁用 / 当前覆盖范围 / 常见用法”
- showcase：再加“项目解决什么问题 / 核心设计 / 示例输出 / 关键文件 / 质量支撑”
-->

## 适合谁用

- <目标用户 1>
- <目标用户 2>
- <目标用户 3>

## 典型场景

<用一个真实、短小的例子说明什么时候会用到这个 skill。不要写成完整工作流，只要让读者一眼看懂“原来可以这样用”。>

```text
用户：<用户会怎么提出需求>
AI：<这个 skill 会如何介入，并产出什么>
```

## 它能产出什么

- <产出物 1>
- <产出物 2>
- <产出物 3>

## 安装方式

1. 打开本仓库的 GitHub Releases。
2. 下载最新版本的 skill 压缩包。
3. 解压后将 `<skill-name>/` 文件夹放入你的 skill 目录。
4. 在支持 `SKILL.md` 的 Agent / Claude 环境中启用该 skill。

<!-- 如果需要依赖，必须就近补充，例如：
5. 安装依赖：`pip install -r scripts/requirements.txt`
6. 配置 API Key：复制 `scripts/.env.example` 为 `scripts/.env` 并填入密钥
-->

<!-- 不要在 README 中写“通过 git subtree 同步”“所有修改在 monorepo 中进行”等内部维护机制。README 面向最终用户，应把这里留给安装、使用和项目导流。 -->

## 可以怎么用

你可以直接向 Agent 提出类似问题：

- “<示例问题 1>”
- “<示例问题 2>”
- “<示例问题 3>”

## 使用边界

这个 skill 适合：

- <适合场景 1>
- <适合场景 2>
- <适合场景 3>

这个 skill 不适合：

- <不适合场景 1>
- <不适合场景 2>
- <不适合场景 3>

<!-- 以下为 standard / showcase profile 可选模块。简单 skill 可以删除。 -->

## 这个项目解决什么问题

<可选。用于复杂或重点推广的 skill。讲真实痛点，不要先讲文件结构。>

## 当前覆盖范围

- <覆盖范围 1>
- <覆盖范围 2>
- <覆盖范围 3>

## 核心设计

### 1. <设计原则 A>

<说明这个设计原则为什么存在，它如何影响输出质量。>

### 2. <设计原则 B>

<说明这个设计原则为什么存在，它如何影响使用体验。>

### 3. <设计原则 C>

<说明这个设计原则为什么存在，它如何控制边界或风险。>

## 示例输出

<可选。放一个短示例即可，不要把完整长文档粘进 README。重点展示“使用后会得到什么”。>

```text
<简短示例输出>
```

## Before / After

不用这个 skill：

- <原来需要手工做什么>
- <容易遗漏什么>

使用这个 skill：

- <现在能自动完成什么>
- <输出如何更稳定、更结构化>

## 项目结构

```text
<skill-name>/
├── SKILL.md
├── CHANGELOG.md
├── LICENSE.txt
├── references/
├── assets/
├── examples/
├── evals/
└── scripts/
```

## 关键文件

- [SKILL.md](./SKILL.md)：正式 skill 入口，供 Agent 判断何时加载和如何执行
- [CHANGELOG.md](./CHANGELOG.md)：版本变更记录
- [LICENSE.txt](./LICENSE.txt)：许可证文本
- [references/](./references/)：领域资料、流程规则或补充说明
- [examples/](./examples/)：公开示例或示范输入输出
- [evals/](./evals/)：评测样本或回归检查
- [scripts/](./scripts/)：辅助脚本

## 质量支撑

- <评测或回归方式 1>
- <示例或样稿 2>
- <脚本或人工检查 3>

## 许可证

本作品采用 [<许可证类型>](<许可证链接>) 许可证。

<!-- CC BY-NC 类 skill 如需提示商用授权，写：
如需商用授权，请以 LICENSE.txt 中的联系方式为准。
-->

## 作者

<从 config/readme-profile.json 的 author.display 读取；如未配置，再从 SKILL.md frontmatter 的 author 字段提取>

<!-- 如 config/readme-profile.json 或环境变量配置了作者咨询入口，可加入二维码或联系方式，例如：

<contact_messages.default / contact_messages.legal / contact_messages.tool 中匹配当前 skill 的联系文案>

<div align="center">
  <img src="<author.qr_image_url>" width="200" alt="微信二维码"/>
  <p><em>微信：<author.wechat_id></em></p>
</div>
-->

## 关联项目

本仓库是 [<upstream.name>](<upstream.url>) 的子项目。<upstream.description>

相关项目：

- [<related_projects 中的相关项目 A>](<URL>)：<一句话说明>
- [<related_projects 中的相关项目 B>](<URL>)：<一句话说明>
- [<related_projects 中的相关项目 C>](<URL>)：<一句话说明>

## 发布前检查

- [ ] 首屏说明了目标用户、核心场景和输出结果
- [ ] 前半部分有真实提问示例
- [ ] 安装步骤可执行，依赖/API Key 说明就近出现
- [ ] 适合/不适合场景分开写清楚
- [ ] 法律、专利、商标、合规类 skill 写明不替代正式专业意见
- [ ] 许可证、作者、关联项目与当前 skill 元数据一致
- [ ] 关联项目面向最终用户导流，不暴露 monorepo/subtree 等内部维护机制
- [ ] 删除模板占位符、内部维护口吻和过长目录树
