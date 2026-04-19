# md2word

将 Markdown 文档转换为符合中文排版标准的专业格式 Word 文档，内置多种预设格式。

> 写 Markdown，出 Word——自动排版，无需手动调格式。

## 典型场景

```text
用户：帮我把这份合同草案转成正式的法律文书 Word 格式
AI：调用 md2word 脚本，使用 legal 预设格式，输出排版规范的 .docx 文件
```

## 它能产出什么

- 符合中文排版标准的 Word 文档
- 多种预设格式（法律文书、学术论文、极简等）
- 自定义配置支持

## 安装方式

1. 打开本仓库的 GitHub Releases。
2. 下载最新版本的 skill 压缩包。
3. 解压后将 `md2word/` 文件夹放入你的 skill 目录。
4. 安装 Python 依赖：`pip install python-docx Pillow beautifulsoup4 PyYAML`

## 使用边界

**适合：**
- Markdown 转 Word 文档
- 需要规范中文排版的正式文档
- 法律文书、学术论文、报告等场景

**不适合：**
- 复杂 Word 模板的精细调整
- 需要高度自定义排版的场景（建议用自定义配置）

## 许可证

本作品采用 [MIT](https://opensource.org/licenses/MIT) 许可证。

## 作者

杨卫薪律师（微信 ywxlaw）

## 关联项目

本仓库是 [legal-skills](https://github.com/cat-xierluo/legal-skills) monorepo 的子项目。所有修改均在 monorepo 中进行，通过 git subtree 同步到本仓库。
