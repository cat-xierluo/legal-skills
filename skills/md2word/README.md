# md2word

将 Markdown 文档转换为符合中文排版习惯的 Word 文档，适合正式报告、法律文书、服务方案、论文和工作材料。

> 写 Markdown，交付 Word。把标题、表格、图片、代码块和基础版式交给脚本处理，减少手动调格式。

## 典型场景

```text
用户：请把这份 Markdown 服务方案转成正式 Word，使用法律服务方案风格。
AI：我会调用 md2word，选择 service-plan 预设，生成排版后的 .docx 文件。
```

## 它能产出什么

- `.docx` Word 文档
- 按预设应用的标题、正文、页边距、表格和代码块样式
- 自动嵌入本地图片和外部 URL 图片
- Mermaid 失败时的降级文本占位
- 可复用的自定义 YAML 配置

## 当前覆盖范围

内置常用预设：

- `legal`：法律文书格式，默认预设
- `service-plan`：法律服务方案，含分层配色
- `minimal`：极简正式文档
- `academic`：学术论文
- `report`：工作报告

完整预设以 `assets/presets/*.yaml` 为准，可运行以下命令查看：

```bash
python scripts/config.py --list
```

## 安装方式

1. 打开本仓库的 GitHub Releases。
2. 下载最新版本的 skill 压缩包。
3. 解压后将 `md2word/` 文件夹放入你的 skill 目录。
4. 安装 Python 依赖：

```bash
pip install python-docx Pillow beautifulsoup4 PyYAML
```

如需渲染 Mermaid 图表，可选安装：

```bash
npm install -g @mermaid-js/mermaid-cli
```

## 可以怎么用

```bash
# 基本转换
python scripts/md2word.py input.md output.docx

# 使用预设
python scripts/md2word.py input.md output.docx --preset legal

# 使用自定义配置
python scripts/md2word.py input.md output.docx --config my-config.yaml
```

也可以直接让 Agent 帮你选择预设：

- “把这份 Markdown 转成正式法律文书 Word”
- “用学术论文格式导出这份论文草稿”
- “把报告转成 Word，外链图片也嵌入进去”

## 使用边界

这个 skill 适合：

- Markdown 到 Word 的批量或重复转换
- 中文正式文档的基础排版
- 需要预设样式、图片、表格和代码块的文档

这个 skill 不适合：

- 精细到每一页版面都要人工设计的复杂 Word 模板
- 依赖 Word 高级域、复杂目录、批注修订或宏的文档
- 从 PDF、扫描件或图片中抽取内容后再排版；这类任务应先用 OCR 或文档解析工具

## 关键文件

- [SKILL.md](./SKILL.md)：Agent 使用入口
- [scripts/md2word.py](./scripts/md2word.py)：主转换脚本
- [references/config-reference.md](./references/config-reference.md)：配置项说明
- [references/style-mappings.md](./references/style-mappings.md)：Markdown 到 Word 样式映射
- [assets/config-template.yaml](./assets/config-template.yaml)：自定义配置模板

## 许可证

本作品采用 [MIT](https://opensource.org/licenses/MIT) 许可证。

## 关于作者 / 咨询与交流

杨卫薪律师（微信 ywxlaw）

如需使用交流、企业内部落地、定制开发或商用授权，欢迎添加微信（请注明来意）。

<div align="center">
  <img src="https://raw.githubusercontent.com/cat-xierluo/legal-skills/main/wechat-qr.jpg" width="200" alt="微信二维码"/>
  <p><em>微信：ywxlaw</em></p>
</div>

## 关联项目

本仓库是 [Legal Skills](https://github.com/cat-xierluo/legal-skills) 的子项目。如果需要合同、商标、专利、OPC、小微企业合规、文档处理等更多法律类开源 Skill，可以关注主仓库。

相关项目：

- [contract-copilot](https://github.com/cat-xierluo/legal-skills/tree/main/skills/contract-copilot)：合同审查、起草和 Word 修订批注
- [legal-proposal-generator](https://github.com/cat-xierluo/legal-skills/tree/main/skills/legal-proposal-generator)：法律服务方案生成
- [de-ai-polish](https://github.com/cat-xierluo/legal-skills/tree/main/skills/de-ai-polish)：中文文章去 AI 腔和自然化润色
