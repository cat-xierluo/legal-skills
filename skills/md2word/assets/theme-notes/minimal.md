# 极简主题样式配置

极简风格，注重内容本身，去除装饰性元素。

## 主题概述

- **名称**: 极简主题
- **适用场景**: 个人笔记、草稿、快速文档
- **风格**: 简洁、无装饰
- **模板文件**: `minimal.docx`

---

## 样式特点

### 标题

- 黑色单色，无彩色装饰
- 字号递减：16pt → 14pt → 12pt
- 微软雅黑字体

### 正文

- 宋体 11pt
- 1.0 倍行距（紧凑）
- 最小段落间距

### 代码

- 等宽字体，无背景色
- 保持原汁原味

---

## 使用方法

```bash
python scripts/extract_template_config.py \
  --template assets/templates/minimal.docx \
  --output assets/presets/minimal.yaml \
  --profile minimal
```

---

## 待修改配置

当前为默认模板副本，需手动调整：

1. 打开 `minimal.docx`
2. 修改标题颜色为黑色 (#000000)
3. 调整正文行距为 1.0
4. 减少段落间距
