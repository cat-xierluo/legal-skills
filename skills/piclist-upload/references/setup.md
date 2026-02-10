# PicList 安装与配置指南

## 什么是 PicList

PicList 是 PicGo 的持续维护版本，提供了更好的用户体验和更多功能。本项目使用 PicList 的内置 HTTP Server 功能来实现图片上传。

## 下载安装

### macOS

```bash
# 通过 Homebrew 安装
brew install --cask piclist
```

或直接下载：https://github.com/Kuingsmile/PicList/releases

### Windows

下载安装包：https://github.com/Kuingsmile/PicList/releases

### Linux

下载 AppImage 或解压包：https://github.com/Kuingsmile/PicList/releases

## 启用 HTTP Server

### 方法一：通过界面启用

1. 打开 PicList 应用
2. 点击左侧「设置」图标
3. 找到「插件设置」→「内置服务器」
4. 勾选「启动内置服务器」
5. 确认端口为 `36677`（默认）

### 方法二：通过配置文件

配置文件位置：
- **macOS**: `~/Library/Application Support/piclist/data.json`
- **Windows**: `%APPDATA%/piclist/data.json`
- **Linux**: `~/.config/piclist/data.json`

添加以下配置：

```json
{
  "picBed": {
    "current": "your-uploader",
    "uploader": "your-uploader",
    "transformer": "path"
  },
  "server": {
    "port": 36677,
    "host": "0.0.0.0",
    "enable": true
  }
}
```

## 配置图床

PicList 支持多种图床服务：

### GitHub

1. 进入「图床设置」→「GitHub图床」
2. 配置参数：
   - **仓库名**: `username/repo`
   - **分支**: `main` 或 `master`
   - **路径**: `images/`（可选）
   - **自定义域名**: `https://cdn.jsdelivr.net/gh/username/repo@main`（可选，用于加速）
3. 设置 Token：
   - 访问 https://github.com/settings/tokens
   - 生成新 Token，勾选 `repo` 权限
   - 粘贴到 Token 字段

### 阿里云 OSS

1. 进入「图床设置」→「阿里云OSS图床」
2. 配置参数：
   - **KeyId**: 阿里云 AccessKey ID
   - **KeySecret**: 阿里云 AccessKey Secret
   - **存储桶名**: Bucket 名称
   - **存储区域**: 如 `oss-cn-shanghai`
   - **存储路径**: 如 `images/`
   - **自定义域名**: 绑定的域名（可选）

### 腾讯云 COS

1. 进入「图床设置」→「腾讯云COS图床」
2. 配置参数：
   - **版本**: v5 或 v4
   - **SecretId**: 腾讯云 SecretId
   - **SecretKey**: 腾讯云 SecretKey
   - **存储桶名**: Bucket 名称
   - **存储区域**: 如 `ap-shanghai`
   - **存储路径**: 如 `images/`
   - **自定义域名**: 绑定的域名（可选）

### SM.MS

1. 进入「图床设置」→「SM.MS图床」
2. 配置参数：
   - **API密钥**: 在 https://sm.ms/home/apitoken 获取

## 验证配置

### 测试 HTTP Server

```bash
curl http://127.0.0.1:36677/upload
```

应返回 HTML 说明页面。

### 测试上传

```bash
curl -X POST "http://127.0.0.1:36677/upload" \
  -F "file=@/path/to/test.png"
```

应返回 JSON 格式的上传结果。

## 官方文档

- 项目地址：https://github.com/Kuingsmile/PicList
- 配置文档：https://piclist.cn/configure
- 常见问题：https://piclist.cn/faq
