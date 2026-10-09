# 应用内更新与热修发布门禁

适用于带 updater 的桌面应用。安装包能打开、资产齐全、JSON 格式正确或单元测试通过，各自只证明一个阶段，不能据此宣布应用内升级成功。

## 1. 先确定旧客户端能走到哪一步

记录实际安装版本、目标版本、失败阶段和原始错误：检查清单 → 下载 → 验签 → prepare → 安装替换 → 重启 → 数据恢复。先保留失败日志，再做最小修复。

- **旧版本在新代码运行前失败**：发布新包不能修复正在执行的旧壳。提供一次手动覆盖安装的引导，说明数据保留和已实测的旧版本范围；不能宣称所有历史版本都能应用内自修复。
- **Fathom 实例**：0.3.6 helper 正常退出，但父壳未回收 Child，`ps -p` 仍看到僵尸 PID，prepare 报 `helper_exit_timeout`，未进入备份或替换。0.4.0 代码仍无该回收修复。新壳修复后仍需验证真实升级，不能用发布新 tar 推断旧壳成功。
- 公钥轮换也是旧客户端能力边界：验签必须对照已安装客户端公钥，不能只使用目标包里的新公钥。

## 2. 资产与标准验签分别验收

对每个实际支持平台核对安装包、updater binary、`.sig`、manifest 的版本与 URL。上传重命名后的确切资产名称是 URL 真值；不要假定所有项目沿用 Tauri 原始文件名。

1. 下载本次候选的真实 tar / exe、`.sig` 与 manifest，保存文件 SHA256、tag、完整 commit OID。
2. manifest 的签名文本须与该平台 `.sig` 内容一致；该检查只是绑定关系，不能证明密码学验签成功。
3. 使用标准 minisign 验证器或客户端所用的 Tauri updater 验证路径，公钥取自旧客户端配置。不得手写二进制偏移、key-id 截取、magic bytes 解析来代替标准验签；解析错误不是签名错误。
4. 原包必须验签成功；修改一字节的副本必须验签失败。记录验证器版本、命令、退出码和所用公钥来源。缺工具时明确 `NOT_VERIFIED`，不自动安装、不关闭签名验证。

Tauri 的公钥和 `.sig` 通常是 base64 编码的 minisign 文本。下面只解码传输封装，实际密码学验证交给 minisign；若项目直接存原始 minisign 文本，则无需解码。使用隔离证据目录，参数按实际路径填写：

```python
import base64
import json
from pathlib import Path

config = json.loads(Path("tauri.conf.json").read_text())
Path("updater.pub").write_bytes(base64.b64decode(
    config["plugins"]["updater"]["pubkey"], validate=True))
Path("updater.minisig").write_bytes(base64.b64decode(
    Path("App.app.tar.gz.sig").read_text().strip(), validate=True))
```

```sh
minisign -Vm App.app.tar.gz -p updater.pub -x updater.minisig
```

不要读取、复制或打印私钥。验签不需要私钥。规范来源：[Tauri updater](https://v2.tauri.app/plugin/updater/)、[minisign 官方验证命令](https://jedisct1.github.io/minisign/)。

## 3. 真实升级与失败恢复矩阵

从当前支持的旧版本 N 到候选 N+1，以隔离安装目录、合成数据和显式隔离的运行根执行真实 `.app`/客户端入口。不扫描真实 HOME，不修改生产调度或权限，不以覆盖旧库作为升级方法。

| 阶段 | 必须观察的结果 | 不能替代它的证据 |
|---|---|---|
| 检查/下载/验签 | 真实客户端识别目标、下载正确字节并通过签名校验 | manifest 的长度/格式正确 |
| 停止与回收 | 旧 helper 退出、父壳回收其 Child、端口释放；无僵尸遗留 | 仅停止 HTTP，或测试额外线程帮助 wait/reap |
| 准备与备份 | 备份存在且可打开，历史内容与恢复材料有效，事务 journal 正确 | prepare 回调 mock 返回 ok |
| 应用替换 | 真实 bundle 被替换，版本和 helper 来源均是候选 | cargo build 或手动复制文件的模拟流程 |
| 重启/恢复 | 新客户端与 helper 重新握手，数据兼容、版本正确、无重复后台服务 | prepare 成功或仅新包 CLI --version |
| 失败恢复 | 注入代表性安装/重启失败后旧 bundle 和数据可恢复、错误在界面可见、重试仍可用 | 只测异常被捕获 |

先复现实际反例，再验证修复。helper 由 Rust 壳创建时，应通过壳持有的 Child 验证回收；Python fixture 添加额外 reaper 可能掩盖生产缺陷。端口释放与 PID 退出分开记录。测试自起服务在所有成功/失败/提前返回路径都须回收并有限退出，不能强制退出掩盖资源泄漏。

可逐阶段记录证据；未执行项保持 `NOT_VERIFIED`。明确区分“旧 helper 在新壳内的 prepare/rollback 已验”和“旧已安装版本完成 GUI 下载/替换/重启已验”。发行合同要求的真实路径未通过时不能公开 Draft；也不能把新账户、Intel 或签名公证验证推断为通过。

## 4. 公开版本保持不变

- 已公开 tag、二进制、签名和 manifest 保留；代码修复发新 patch，例如已有 0.4.0 就发布 0.4.1。
- 候选构建前冻结完整 commit OID，先运行项目 CI/本地构建，不反复打 tag 看能否构建。
- Draft 的重传先只读检查 `isDraft=true`、目标 tag/commit 正确，再上传；不能先 `--clobber` 再断言 Draft。存在并发发布者时串行核对；无法证明状态则停止上传。
- 固定候选的 transient 构建故障可重跑同一 workflow；候选代码改变后重新审查、验证。公开之后再修代码仍用新 patch。
- 真实安装/更新阻断 hotfix 可在用户明确授权下不足24小时发布，需保留实质修复、复现与最终候选证据；纯文档、typo 或未知失败不适用。

## 5. Release Notes 必须解释用户该怎么升级

说明修复了哪个阶段、哪些已安装版本需要一次手动覆盖、手动安装是否保留历史、平台与签名限制，以及实际验证范围。不要写“已下载新包，所以旧客户端已修复”。公开后用未认证的公共 URL 检查下载与更新源可达，并复核最终 manifest 指向本次确切资产。
