# 使用说明

## 配置步骤

### 1. 复制配置文件

```bash
cd test/douyin-batch-download
cp config/config.yaml.example config/config.yaml
```

### 2. 配置 Cookie

**方式一：扫码登录（推荐）**

```bash
python scripts/login.py
```

脚本会自动打开浏览器显示二维码，扫码登录后自动保存 Cookie。

**方式二：手动配置**

编辑 `config/config.yaml`，填写 `cookie` 字段：

```yaml
cookie:
  auto_extract: true    # 优先从浏览器自动读取
  manual: "ttwid=xxx; sessionid=yyy; ..."
```

### 3. Cookie 获取方式

- **扫码登录**：运行 `python scripts/login.py`
- **手动获取**：从浏览器开发者工具复制

## 快速开始

```bash
# 单个博主下载
/douyin-batch-download "https://www.douyin.com/user/MS4wLjABAAAA..."

# 批量下载多个博主
/douyin-batch-download \
    "博主A" "https://www.douyin.com/user/MS4wLjABBBB..." \
    "博主B" "https://www.douyin.com/user/MS4wLjABCCC..."

# 增量更新（只下载新视频）
/douyin-batch-download --update
```

## 关注列表管理

使用 `manage-following.py` 脚本动态管理关注列表（**不影响已下载的视频文件**）：

```bash
# 查看关注列表
python scripts/manage-following.py --list

# 通过主页链接添加用户（推荐方式）
python scripts/manage-following.py --add "https://www.douyin.com/user/MS4wLjABAAAA..."

# 删除关注（保留视频文件）
python scripts/manage-following.py --remove 2722012335188296

# 搜索用户（按昵称/简介/UID）
python scripts/manage-following.py --search "张总"
```

> **注意**：
>
> - 请通过**主页链接**方式添加用户（`--add`），不要使用 `add-user-by-uid.py`
> - 直接 UID 方式获取用户信息不稳定，可能会失败
> - 直接 UID 方式获取用户信息不稳定，可能会失败

### 管理命令说明

| 命令 | 说明 |
|:-----|:------|
| `--list` | 显示所有关注用户及统计信息 |
| `--add <url>` | 通过主页链接添加用户到关注列表 |
| `--remove <uid>` | 删除关注（视频文件保留） |
| `--search <关键词>` | 按昵称/简介/UID搜索用户 |

## 命令参数

### 下载参数

| 参数 | 说明 |
|:-----|:------|
| `<url>` | 抖音主页链接或博主 ID |
| `--limit <n>` | 限制下载数量 |
| `--update` | 启用差量更新模式 |
| `--list` | 显示已下载博主列表 |
| `--cookie` | 手动指定 Cookie 字符串 |
| `--help` | 显示帮助信息 |

### 压缩参数

使用 ffmpeg 压缩视频以节省存储空间：

| 参数 | 说明 |
|:-----|:------|
| `--compress` | 压缩全部视频 |
| `--compress --user <uid>` | 压缩指定用户视频 |
| `--compress --file <video.mp4>` | 压缩单个视频文件 |
| `--compress --replace` | 压缩后替换原文件（默认保留） |
| `--compress --crf <n>` | 设置压缩质量 (0-51, 默认28) |
| `--compress --preset <level>` | 压缩速度预设 (fast/medium/slow等) |
| `--compress --no-skip-small` | 不跳过小文件（默认跳过<5MB的文件） |

**示例：**

```bash
# 压缩全部视频
python scripts/compress.py

# 压缩指定用户
python scripts/compress.py --user 123456789

# 压缩单个文件
python scripts/compress.py --file video.mp4

# 压缩后替换原文件
python scripts/compress.py --replace
```

## Web 管理界面

**简洁方案（推荐）**：双击直接打开，无需服务器

```bash
# 1. 生成数据文件
python scripts/generate-data.py

# 2. 直接用浏览器打开 index.html（或双击文件）
open /Users/maoking/Library/Application\\ Support/maoscripts/skills/legal-skills/test/douyin-batch-download/downloads/index.html
```

**功能**：
- 博主列表视图 - 展示所有已下载的博主
- 视频网格视图 - 展示所有下载的视频
- 点击博主卡片可查看该用户的视频
- 搜索过滤 - 实时搜索博主或视频
- 统计信息 - 博主数、视频数、占用空间

**更新数据**：
下载视频后会自动生成 `data.js`，无需手动操作。
压缩视频后，运行 `python scripts/generate-data.py` 即可更新数据。

## 输出目录结构

```
{download_path}/{数字ID}/
├── 视频/           # {aweme_id}.mp4
├── 封面/           # {aweme_id}.webp（可选）
└── 转录文字/        # {aweme_id}.md（预留）
```

## 配置文件

`config/config.yaml`：

```yaml
# Cookie 配置
cookie:
  auto_extract: true    # 优先从浏览器自动读取
  manual: ""            # 失败时手动填写

# 下载配置
download_path: "/path/to/downloads"
naming_template: "{create}_{desc}_{aweme_id}"

# 增量模式
incremental:
  enabled: true
  mode: "diff"         # diff: 只下载新视频

# Cookie 有效期提醒
cookie_expiry_days: 14
```

## 差量更新逻辑

使用 `--update` 参数时：
1. 获取主页所有视频 ID
2. 对比本地已下载列表
3. 只下载主页中有但本地没有的视频

## 注意事项

- **Cookie 有效期**：建议 7-14 天更新一次
- **请求频率**：避免过快请求，防止被风控
- **法律合规**：仅供个人学习研究使用
