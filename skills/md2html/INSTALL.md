# 依赖安装指南

## 系统要求

- Python 3.8+
- pip

## 安装步骤

### 方式一：使用虚拟环境（推荐）

```bash
# 进入 skill 目录
cd /path/to/md2html

# 创建虚拟环境
python3 -m venv .venv

# 激活虚拟环境
source .venv/bin/activate  # macOS/Linux
# 或
.venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

### 方式二：使用 pipx（推荐用于命令行工具）

```bash
# 安装 pipx（如果未安装）
brew install pipx

# 安装依赖
pipx install markdown beautifulsoup4
```

### 方式三：使用 --user 标志

```bash
pip install --user -r requirements.txt
```

## 验证安装

```bash
python scripts/md2html.py --help
```

## 可选依赖

```bash
# 代码语法高亮
pip install pygments

# PDF 直接导出
pip install weasyprint
```
