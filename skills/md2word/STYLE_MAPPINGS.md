# Markdown 到 Word 样式映射

本文档定义了 Markdown 元素如何映射到 Word 文档样式。

## 默认映射

转换器使用以下默认映射：

| Markdown 元素 | Word 样式 | 说明 |
|--------------|-----------|------|
| `# 标题 1` | Heading 1 | 16 pt，加粗 |
| `## 标题 2` | Heading 2 | 14 pt，加粗 |
| `### 标题 3` | Heading 3 | 13 pt，加粗 |
| `#### 标题 4` | Heading 4 | 12 pt，加粗 |
| `##### 标题 5` | Heading 5 | 11 pt，加粗，斜体 |
| `###### 标题 6` | Heading 6 | 11 pt，斜体 |
| 普通文本 | Normal | 12 pt，1.5 倍行距，首行缩进 |
| `> 引用` | Block Quote | 缩进，灰色背景 |
| `    代码块` | Code Block | 等宽字体，灰色背景 |
| `` `行内代码` `` | Code Char | 等宽字体，品红色 |
| `*斜体*` | Emphasis | 斜体 |
| `**粗体**` | Strong | 加粗 |
| `***粗斜体***` | Intense Emphasis | 加粗，强调色 |
| `- 项目` | List Bullet | 项目符号列表 |
| `1. 项目` | List Number | 编号列表 |

## 样式自定义

### 通过配置文件

创建 YAML 配置文件来自定义样式：

```yaml
fonts:
  default:
    name: "仿宋_GB2312"
    ascii: "Times New Roman"
    size: 12

titles:
  level1:
    size: 16
    bold: true
    color: "#1A1A2E"
```

### 通过 Word 模板

将 `.docx` 模板放入 `assets/templates/` 目录，转换时会应用模板中的样式定义。

## 在 Word 中创建自定义样式

### 方法：通过 Word 界面

1. 在 Word 中打开模板文件
2. 转到 **开始** → **样式** 窗格（启动器图标）
3. 右键点击样式 → **修改...**
4. 调整格式设置
5. 点击 **确定**
6. 保存模板文件

## 常见自定义

### 修改标题颜色

在 Word 中修改 `Heading 1` 样式：
- 右键点击 **Heading 1** → **修改...**
- **格式** → **字体...**
- 设置字体颜色
- 点击 **确定**

### 调整代码块背景

在 Word 中修改 `Code Block` 样式：
- 右键点击 **Code Block** → **修改...**
- **格式** → **边框...**
- **底纹** 选项卡
- 选择填充颜色
- 点击 **确定**

### 自定义列表缩进

在 Word 中修改列表样式：
- 右键点击 **List Bullet** → **修改...**
- **格式** → **编号...**
- 调整缩进
- 点击 **确定**

## 映射故障排除

### 样式未应用

**症状**: 文本未使用预期样式

**解决方案**:
1. 验证配置文件中的样式名称完全匹配
2. 检查预设 YAML 是否存在且格式正确
3. 确保 Word 模板中的样式名称与配置一致

### TOC 未生成

**症状**: 目录缺失

**解决方案**:
1. 确认 Markdown 中使用了 `#` 标题语法
2. 验证 Heading 1-3 样式存在
3. 在 Word 中：**引用** → **目录** → **更新**

### 中文字体错误

**症状**: 中文文本使用回退字体

**解决方案**:
1. 安装思源宋体 (Source Han Serif CN)
2. 在样式中修改为优先使用系统字体：
   - macOS: 宋体-简 (Songti SC)
   - Windows: 宋体 (SimSun)

## 测试映射

修改配置后，测试转换：

```bash
# 使用预设转换
python scripts/md2word.py input.md --preset=legal -o test.docx

# 使用自定义配置转换
python scripts/md2word.py input.md --config=my-config.yaml -o test.docx

# 打开并验证样式
open test.docx  # macOS
```

## 参考样式名称

Word 文档中定义的所有样式（节选）：

- Heading 1, Heading 2, Heading 3, Heading 4, Heading 5, Heading 6
- Normal, Body Text, Body Text 2, Body Text 3
- Block Quote
- Code Block, Code Char
- Emphasis, Strong, Intense Emphasis
- List Bullet, List Number, List Paragraph
- Footer, Header
- Book Title
- Intense Quote

查看完整列表，在 Word 中打开模板文件：
**开发工具** 选项卡 → **样式** 检查器（或 **开始** → 样式窗格）
