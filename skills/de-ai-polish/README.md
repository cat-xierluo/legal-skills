# de-ai-polish

检测并去除文章中的 AI 化表述模式，让文字回归自然。

> 一键识别"AI 腔"——对比句式、空洞总结、排比滥用，统统帮你改掉。

## 典型场景

```text
用户：这篇文章读起来太 AI 了，帮我润色一下
AI：我来扫描文中的 AI 化表述模式（对比句式、排比堆砌、空洞总结等），逐条标注并给出改写建议
```

## 它能产出什么

- AI 化表述的全文检测报告
- 逐条改写建议（删/合并/改写三种策略）
- 直接修正后的干净文本

## 安装方式

1. 打开本仓库的 GitHub Releases。
2. 下载最新版本的 skill 压缩包。
3. 解压后将 `de-ai-polish/` 文件夹放入你的 skill 目录。
4. 在支持 `SKILL.md` 的 Agent / Claude 环境中启用该 skill。

## 使用边界

**适合：**
- 去除 AI 生成文本中的典型模式化表述
- 文章润色和写作风格统一
- 中文学术、公文、自媒体文章

**不适合：**
- 英文文本处理
- 专业术语或固定法律用语的修改（这些不属于 AI 腔）

## 许可证

本作品采用 [MIT](https://opensource.org/licenses/MIT) 许可证。

## 作者

杨卫薪律师（微信 ywxlaw）

## 关联项目

本仓库是 [legal-skills](https://github.com/cat-xierluo/legal-skills) monorepo 的子项目。所有修改均在 monorepo 中进行，通过 git subtree 同步到本仓库。
