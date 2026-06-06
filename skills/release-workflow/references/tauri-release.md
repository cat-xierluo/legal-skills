# Tauri 桌面应用发布指南

基于 Tauri v2 的桌面应用发布特有事项。

## CI 工作流配置

推荐使用 `tauri-apps/tauri-action`，分离 build 和 publish 两个 job：

```yaml
name: release

on:
  push:
    tags:
      - 'v*'

permissions:
  contents: write

concurrency:
  group: release-${{ github.ref_name }}
  cancel-in-progress: true

jobs:
  build:
    strategy:
      fail-fast: false
      matrix:
        include:
          - platform: macos-latest
            args: --target aarch64-apple-darwin
          - platform: macos-latest
            args: --target x86_64-apple-darwin
          - platform: windows-latest
            args: ''
    runs-on: ${{ matrix.platform }}
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 10

      - uses: dtolnay/rust-toolchain@stable
        with:
          targets: ${{ matrix.platform == 'macos-latest' && 'aarch64-apple-darwin,x86_64-apple-darwin' || '' }}

      - uses: Swatinem/rust-cache@v2
        with:
          workdir: src-tauri

      - run: pnpm install

      - uses: tauri-apps/tauri-action@v0
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          # 仅自动更新需要：签名密钥
          TAURI_SIGNING_PRIVATE_KEY: ${{ secrets.TAURI_SIGNING_PRIVATE_KEY }}
          TAURI_SIGNING_PRIVATE_KEY_PASSWORD: ${{ secrets.TAURI_SIGNING_PRIVATE_KEY_PASSWORD }}
        with:
          tagName: ${{ github.ref_name }}
          releaseName: 'App ${{ github.ref_name }}'
          releaseDraft: true
          prerelease: false
          # 不用自动更新时设为 false，用自动更新时设为 true
          includeUpdaterJson: false
          args: ${{ matrix.args }}

  # 仅自动更新需要此 job：生成 latest.json 并发布
  publish:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Generate latest.json
        run: |
          # 从 draft release 下载 .sig 文件，生成 latest.json
      - name: Upload and publish
        run: |
          gh release upload "${{ github.ref_name }}" latest.json --clobber
          gh release edit "${{ github.ref_name }}" --draft=false
```

## 配置要点

### 包管理器

跨平台构建（macOS + Windows）推荐 pnpm。npm/bun 存在 optional dependencies bug，macOS lock file 不包含 Windows 原生绑定。

仅构建 macOS 时 `npm ci` 可用，但统一使用 pnpm 可避免后续扩展 Windows 矩阵时踩坑。

### includeUpdaterJson

`includeUpdaterJson: false` + 手动生成 `latest.json` 可精确控制平台键名和 URL 格式，避免 tauri-action 内置生成器产生冗余键。

### 分离 build 和 publish

单 job 模式无法在发布前验证所有平台构建成功，也无法在发布前自定义 `latest.json`。build job 上传到 draft release，publish job 在全部成功后发布。

### concurrency

移动 tag 会触发重复构建，添加 `concurrency` 配置避免。

## 构建产物

### 仅安装包（不需要自动更新）

Pake 等项目只发布安装包，不包含更新器产物。适用于用户手动下载更新的场景。

| 平台 | 安装包 |
|------|--------|
| macOS ARM | `App_X.Y.Z_aarch64.dmg` |
| macOS Intel | `App_X.Y.Z_x64.dmg` |
| Windows | `App_X.Y.Z_x64-setup.exe` |

### 带自动更新

lencx/ChatGPT 等项目在安装包之外，还包含更新器所需的产物。更新器通过 `latest.json` 检查版本、下载对应平台 bundle、用 `.sig` 验证完整性。

| 平台 | 安装包 | 更新器产物 | 签名 |
|------|--------|-----------|------|
| macOS ARM | `App_X.Y.Z_aarch64.dmg` | `App_aarch64.app.tar.gz` | `.sig` |
| macOS Intel | `App_X.Y.Z_x64.dmg` | `App_x64.app.tar.gz` | `.sig` |
| Windows | `App_X.Y.Z_x64-setup.exe` | — | `.exe.sig` |

Windows 只需 `.exe`（NSIS），不需要额外发布 `.msi`。签名文件 `.sig` 和 `latest.json` 一起放在 release assets 中，更新端点直接用 GitHub 直链：

```
https://github.com/<owner>/<repo>/releases/latest/download/latest.json
```

## latest.json 格式

Tauri updater 需要一个 `latest.json`，包含版本号、签名和各平台下载 URL。

```json
{
  "version": "X.Y.Z",
  "notes": "发布说明",
  "pub_date": "2026-05-20T00:00:00Z",
  "platforms": {
    "darwin-aarch64": { "signature": "...", "url": "..." },
    "darwin-x86_64": { "signature": "...", "url": "..." },
    "windows-x86_64": { "signature": "...", "url": "..." }
  }
}
```

平台键名必须使用标准格式（`darwin-aarch64` / `darwin-x86_64` / `windows-x86_64`），避免 `darwin-aarch64-app` 等非标准键名。

## 国内镜像同步

目标用户包含国内用户时，可在 publish job 中同步到 Gitee：创建 Gitee Release → 上传构建产物 → 生成 Gitee 专属 `latest.json` → 上传。

需要 GitHub Secrets：`GITEE_TOKEN`、`GITEE_OWNER`。

Gitee 没有 `releases/latest/download/` 直链，作为 updater endpoint 前需验证可访问性。

## 跨平台 CI 必踩坑（stable Rust 2026-05 之后 + tauri-plugin-updater）

下面这些坑是真实项目里 4 轮 CI 全 fail 的根因。**新项目第一次配 release.yml 前必看**，避免重蹈。

### 1. `universal-apple-darwin` rust-std 在 stable Rust 2026-05 之后被移除

`dtolnay/rust-toolchain@stable` 装 rustup 时不再带 `universal-apple-darwin` rust-std component。`cargo tauri build --target universal-apple-darwin` 报：

```
component 'rust-std' for target 'universal-apple-darwin' is unavailable for download
```

**修法**：`matrix.macos-universal.rust_targets` 拆成两个 underlying arch target，让 Tauri CLI 用 lipo 合并：

```yaml
- label: macos-universal
  os: macos-latest
  target: universal-apple-darwin  # Tauri CLI 识别这个 target 名
  rust_targets: aarch64-apple-darwin,x86_64-apple-darwin  # rustup 装这两个
  bundles: app,dmg
  artifact_glob: |
    src-tauri/target/universal-apple-darwin/release/bundle/macos/*.app
    src-tauri/target/universal-apple-darwin/release/bundle/macos/*.app.tar.gz
    src-tauri/target/universal-apple-darwin/release/bundle/dmg/*.dmg
```

### 2. jammy (Ubuntu 22.04) 仓库无 `libappindicator3-dev`

`sudo apt-get install libappindicator3-dev` 报：

```
libappindicator3-dev : Depends: libappindicator3-1 ... 
libayatana-appindicator3-dev : Conflicts: libappindicator3-dev
```

**修法**：apt 列表里只装 `libayatana-appindicator3-dev`（jammy 唯一可用变体）：

```yaml
- name: Install Linux system dependencies
  if: matrix.os == 'ubuntu-22.04'
  run: |
    sudo apt-get update
    sudo apt-get install -y \
      libwebkit2gtk-4.1-dev \
      librsvg2-dev \
      patchelf \
      build-essential \
      curl \
      wget \
      file \
      libxdo-dev \
      libssl-dev \
      libayatana-appindicator3-dev   # ← 唯一可用变体
```

### 3. Windows runner 默认 shell 是 PowerShell 7

多行 `cargo tauri build \` 反斜杠续行在 PowerShell 7（`pwsh.EXE`）下被吃掉，下一行 `--target` 变 PowerShell 表达式：

```
ParserError: ...ps1:3
Line |   3 |   --target x86_64-pc-windows-msvc \
     |     ~
     | Missing expression after unary operator '--'.
```

**修法**：在 Build Tauri bundle step 显式 `shell: bash`（GitHub Actions Windows runner 自带 Git Bash），三平台都走 bash 续行一致：

```yaml
- name: Build Tauri bundle
  env: ...
  shell: bash   # ← 关键
  run: |
    cargo tauri build \
      --target ${{ matrix.target }} \
      --bundles ${{ matrix.bundles }}
```

### 4. `concurrency.cancel-in-progress: false` 会卡住重试链

`cancel-in-progress: false` 时，移动 tag 触发的第二次 run 排在前一个之后，前一个 cancelled 但 slot 还没释放，新 run 一直 pending 几分钟。

**修法**：用 `cancel-in-progress: true`，新 run 立刻抢占 slot：

```yaml
concurrency:
  group: release-${{ github.ref_name }}
  cancel-in-progress: true
```

### 5. GitHub release CDN 同步延迟（5-15 分钟）

新 release 的公共 URL `https://github.com/<owner>/<repo>/releases/latest/download/latest.json` 在 git push tag 后 5-15 分钟内会 404（CDN 同步延迟），但 `gh release view` / `gh release download` / GitHub API 已经能正常访问（走另一 endpoint）。

**临时验证**用 `gh release download`：

```bash
gh release download v0.1.0 --pattern 'latest.json' --dir /tmp/check
```

**不要**因为 curl 404 就删 release 重发——asset 已经在 release 上了，重发会引入新 asset hash 不一致。

### 6. 升级 keypair / pubkey 时所有相关文件都要改

Tauri updater 的信任链涉及 **3 个地方**：

| 位置 | 字段 | 期望格式 |
|------|------|----------|
| GitHub Secret | `TAURI_SIGNING_PRIVATE_KEY` | 文件原文（一层 base64，**不要**再 `base64 -w0`） |
| `src-tauri/tauri.conf.json` | `plugins.updater.pubkey` | `base64(2 行 minisign 公钥文件内容)`（含 `untrusted comment: minisign public key: <KEYNUM>` header） |
| GitHub Secret | `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` | 私钥加密时用的密码明文 |

只改其中一处会断链。验：`TAURI_PRIVATE_KEY="$(cat ~/.tauri/<key>)" TAURI_PRIVATE_KEY_PASSWORD="..." cargo tauri signer sign /tmp/test.txt` 本地能跑通即 Secret + 密码对。

### 7. `cargo tauri signer --help` 会 dump 环境变量明文

clap 把 env var 默认值显示在 `--help` 输出里。如果 shell session 已经 export 了 `TAURI_PRIVATE_KEY_PASSWORD`，跑 `cargo tauri signer sign --help` 会把密码明文 print 到 stderr —— 进 transcript / CI log。

**修法**：在含密钥的 shell session 里**不要**跑 `cargo tauri signer --help` / `sign --help` 之类。需要查用法时新开一个干净 shell（不 source 含密钥的 env），或查源码（`crates/tauri-cli/src/signer.rs`）。

## 完整 SOP（首次配 + 升级）

1. 一次性：`cargo tauri signer generate -p "<STRONG_PASSWORD>" -w ~/.tauri/<project>.key`
2. 写 `tauri.conf.json` `pubkey`：`base64 -w0 < (cat ~/.tauri/<project>.key.pub | base64 -d)`
3. `gh secret set TAURI_SIGNING_PRIVATE_KEY < ~/.tauri/<project>.key`（直接灌文件，**不要** `base64 -w0`）
4. `gh secret set TAURI_SIGNING_PRIVATE_KEY_PASSWORD "<STRONG_PASSWORD>"`
5. 本地试签验证三件套对：env 灌齐 `cargo tauri signer sign /tmp/test.txt`
6. `git tag vX.Y.Z && git push origin vX.Y.Z` 触发 release.yml
