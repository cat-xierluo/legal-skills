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
