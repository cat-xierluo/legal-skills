# CI/CD 故障排查手册

通用 GitHub Actions 发布工作流的常见问题和解决方案。

## 1. 跨平台原生绑定缺失

**症状**：macOS 构建成功，Windows 构建安装依赖时报找不到平台特定的原生模块。

**原因**：npm/bun 的 optional dependencies bug（npm/cli#4828）。在一个平台生成的 lock file 不包含其他平台的可选依赖。

**解决方案**：
- 改用 pnpm（推荐）：pnpm 在每个 CI runner 上独立解析 optional dependencies
- 或在 Windows 步骤中显式安装缺失的包：`npm install @package/win32-x64-msvc`

## 2. `rm -f` 在 PowerShell 报错

**症状**：Windows runner 上 `rm -f file` 报 `-f` 参数歧义。

**原因**：PowerShell 的 `rm` 是 `Remove-Item` 别名，`-f` 被解析为 `-Filter`。

**解决方案**：使用跨平台兼容命令，或用条件判断 `if: runner.os == 'Windows'` 分开处理。

## 3. tag 触发的重复构建

**症状**：移动 tag 后同时触发新旧两个构建。

**解决方案**：添加 concurrency 配置：

```yaml
concurrency:
  group: release-${{ github.ref_name }}
  cancel-in-progress: true
```

## 4. GitHub token 缺少 workflow 权限

**症状**：推送 `.github/workflows/` 文件被拒绝。

**解决方案**：
```bash
gh auth refresh -h github.com -s workflow
```

## 5. 构建超时

**症状**：Rust 编译或 npm install 超过 GitHub Actions 默认 6 小时限制。

**解决方案**：
- 启用依赖缓存（`Swatinem/rust-cache`、`actions/cache`）
- 使用 `CARGO_INCREMENTAL: 0` 和 `CARGO_TERM_COLOR: always` 优化 Rust 编译
- 拆分构建矩阵为多个独立 job

## 6. Tauri `TAURI_SIGNING_PRIVATE_KEY` Secret 解析失败（minisign 解不出）

**症状**：Build Tauri bundle 阶段（`cargo tauri build` 触发 tauri-plugin-updater 自动签名）报：

```
Error failed to decode secret key: incorrect updater private key password:
  Missing encoded key in secret key
```

**原因**：`TAURI_SIGNING_PRIVATE_KEY` env var 被多层 base64 编码了。`cargo tauri signer generate` 输出的 `.key` 文件本身已经是一层 base64（348 字节单行），如果 Secret 灌之前再 `cat | base64 -w0` 又包一层（double-base64），minisign 解码就拿到 base64 字符流，不是合法 minisign 私钥 blob。

**解决方案**：
- Secret 直接灌文件原文（一层 base64）：
  ```bash
  gh secret set TAURI_SIGNING_PRIVATE_KEY < ~/.tauri/faropdf.key
  ```
- 验证：本地试签一遍能跑通即正确：
  ```bash
  TAURI_PRIVATE_KEY="$(cat ~/.tauri/faropdf.key)" \
  TAURI_PRIVATE_KEY_PASSWORD="..." \
  cargo tauri signer sign /tmp/test.txt
  # 应该输出 "Your file was signed successfully"
  ```
- 相关：`tauri.conf.json` 的 `pubkey` 字段也要求 `base64(2 行 minisign 公钥文件内容)`（含 `untrusted comment: minisign public key: <KEYNUM>` header 行），不是 `.pub` 文件第二行原文 `RWS8...`。详见 `references/tauri-release.md` §3 密钥链

## 7. Tauri `pubkey` 字段格式错

**症状**：Build Tauri bundle 阶段报：

```
Error failed to decode pubkey: failed to decode base64 pubkey:
  failed to convert base64 to utf8: invalid utf-8 sequence of 1 bytes from index 2
```

或后续报：

```
failed to convert updater pubkey: Missing encoded key in public key
```

**原因**：Tauri CLI 的 `decode_key` 函数（`crates/tauri-cli/src/helpers/updater_signature.rs`）对 `pubkey` 字段值先 base64-decode 再 UTF-8 转换，然后 `PublicKeyBox::from_string` 解析。

- 填原文 `RWS8WkTIW8ht2pmQPiablJPY8vRrsXleS6NxLsalJ/Tyn+1tKpHGxREc` → base64-decode 得到二进制 minisign 公钥 bytes（不是 UTF-8）→ `str::from_utf8` 失败
- 填 `base64(RWS8...)` 单行（缺 minisign 2 行 header）→ base64-decode 通过但 `from_string` 拿到单行不合法 box → `into_public_key` 报 "Missing encoded key in public key"

**解决方案**：字段值 = `base64(2 行 minisign 公钥文件内容)`：

```bash
PUBKEY_B64=$(cat ~/.tauri/faropdf.key.pub | base64 -d | base64 -w0)
# 验：echo -n "$PUBKEY_B64" | base64 -d 应回显两行（含 untrusted comment + RWS8...）
```

写入 `tauri.conf.json` 的 `plugins.updater.pubkey`。

## 8. Windows runner 多行 `cargo tauri build \` 反斜杠被 PowerShell 吃掉

**症状**：Windows runner 的 Build Tauri bundle step 报：

```
ParserError: ...ps1:3
Line |   3 |   --target x86_64-pc-windows-msvc \
     |     ~
     | Missing expression after unary operator '--'.
```

**原因**：Windows runner 默认 shell 是 PowerShell 7 (pwsh.EXE)，`\` 反斜杠在 PowerShell 里**不是**行续字符。下一行 `--target` 被解析成 PowerShell 表达式 `--` unary operator。macOS / Linux 默认 bash 续行正常，没暴露。

**解决方案**：在 Build Tauri bundle step 显式 `shell: bash`（GitHub Actions Windows runner 自带 Git Bash）：

```yaml
- name: Build Tauri bundle
  env: ...
  shell: bash   # ← 关键：Windows 也走 Git Bash，跟 macOS / Linux 一致
  run: |
    cargo tauri build \
      --target ${{ matrix.target }} \
      --bundles ${{ matrix.bundles }}
```

## 9. Tauri updater manifest URL 子目录错（`create-updater-manifest.mjs` 之类自写脚本）

**症状**：release assets 都在 release 根目录（如 `FaroPDF_0.1.0_amd64.AppImage`），但 `latest.json` 的 url 指向子目录：

```json
"url": "https://github.com/.../releases/download/0.1.0/faropdf-linux-x64/appimage/FaroPDF_0.1.0_amd64.AppImage"
```

updater 客户端按这个 url 拉会 404（`releases/download/.../<name>` 不带子目录）。

**原因**：
- `softprops/action-gh-release@v2` 用 `files: artifacts/**/*.dmg` glob 上传时**只用 basename**（`actions/download-artifact@v4` 拉到本地时按 artifact 名分子目录，但上传时软化）
- 自写 manifest 脚本用 `relative(releaseDir, file)` 算 url，把 artifact 名子目录带进去了

**解决方案**：自写 manifest 脚本里 url 用 `basename(file)`，不要用 `relative(releaseDir, file)`：

```js
// 错的
const url = buildAssetUrl(args.repo, args.tag, relative(releaseDir, file));

// 对的
import { basename, ... } from "node:path";
const url = buildAssetUrl(args.repo, args.tag, basename(file));
```

## 10. 重新发布后 CDN 同步延迟（公共 URL 5-15 分钟 404）

**症状**：`gh release view` / `gh release download` 能正常列出 / 下载 assets（走 GitHub API），但 `curl https://github.com/.../releases/latest/download/latest.json` 公共 CDN URL 一直 404。

**原因**：GitHub release asset 的 CDN 同步到公共 `releases/download/...` URL 需要 5-15 分钟（gh CLI/API 用的是另一个 endpoint，先于公共 CDN 生效）。

**解决方案**：
- 临时验证用 `gh release download` 或 `gh api repos/<owner>/<repo>/releases/tags/<tag>` 走 API 路径
- 等 15 分钟后再用 curl 测公共 URL
- 客户端（tauri-plugin-updater）第一次检查更新失败时会有 fallback 重试机制，不影响最终升级
- **不要**因为 curl 404 就立刻删 release 重发——asset 已经在 release 上了，重发反而引入新 asset hash 不一致
