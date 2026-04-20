# <skill-name>

<一句话说明：这个 skill 帮谁，在什么场景下，完成什么结果。>

> <一句话价值主张：它能帮用户省掉什么麻烦，或让用户原来做不到的事变得可做。>

<!--
README.md 面向独立 GitHub 仓库的人类访客，不是 skill runtime 文件。
Release zip / 安装包中仍应排除 README.md，避免污染实际 skill 目录。

写作原则：
- outcome first：先讲结果，不先讲 YAML/frontmatter/文件结构
- example first：尽早给一个真实使用场景
- boundary clear：说明适合什么、不适合什么
- install easy：让用户知道如何下载、安装和开始试用

复杂度 profile：
- minimal：保留“典型场景 / 能产出什么 / 安装方式 / 使用边界 / 许可证 / 作者 / 关联项目”
- standard：再加“适合谁用 / 当前覆盖范围”
- showcase：再加“项目解决什么问题 / 核心设计 / 示例输出 / 项目结构 / 质量支撑”
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

> 如果你是从 monorepo 开发者视角维护本项目，请不要直接修改独立仓库。所有修改都应在 monorepo 中完成，再通过 git subtree 同步。

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

## 作者

<从 SKILL.md frontmatter 的 author 字段提取>

## 关联项目

本仓库是 [legal-skills](https://github.com/cat-xierluo/legal-skills) monorepo 的子项目。所有修改均在 monorepo 中进行，通过 git subtree 同步到本仓库。
