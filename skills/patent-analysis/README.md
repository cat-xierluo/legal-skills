# patent-analysis

系统化分析专利文件，支持侵权评估、技术特征提取、权利要求比对等 7 种核心场景。

> 给你一份专利文件，从权利要求拆解到侵权比对，输出结构化分析报告。

## 典型场景

```text
用户：帮我分析一下这件专利和我们产品的侵权风险
AI：我来拆解权利要求、提取技术特征，与你的产品方案逐项比对，输出侵权分析报告
```

## 它能产出什么

- 权利要求技术特征拆解表
- 侵权比对分析报告（全面覆盖原则 + 等同原则）
- 专利稳定性分析、价值评估
- FTO（自由实施）分析

## 安装方式

1. 打开本仓库的 GitHub Releases。
2. 下载最新版本的 skill 压缩包。
3. 解压后将 `patent-analysis/` 文件夹放入你的 skill 目录。
4. 在支持 `SKILL.md` 的 Agent / Claude 环境中启用该 skill。

## 使用边界

**适合：**
- 专利文件的结构化分析
- 侵权风险初步评估
- 权利要求比对和 FTO 分析

**不适合：**
- 替代专利律师的正式法律意见
- 专利无效宣告程序的深度分析
- 跨国专利纠纷的全面评估

## 许可证

本作品采用 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) 许可证。

## 作者

杨卫薪律师（微信 ywxlaw）

## 关联项目

本仓库是 [legal-skills](https://github.com/cat-xierluo/legal-skills) monorepo 的子项目。所有修改均在 monorepo 中进行，通过 git subtree 同步到本仓库。
