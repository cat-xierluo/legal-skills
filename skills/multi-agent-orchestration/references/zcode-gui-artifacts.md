# zcode-gui-artifacts —— 跨机 artifact 安全打包与收件

配套脚本：`scripts/zcode-gui-artifacts.py`（纯标准库，Python 3.9+）、`scripts/test-zcode-gui-artifacts.py`（定向测试）。

## 目的

远端 GUI 任务无法 push 时，人工 base64 回传 bundle 曾出现截断、缺 marker、offset 错误，收件方需要重复劳动校验。本工具用"显式 manifest + 有界 chunk + 完整摘要验证"替代裸 base64 粘贴，使截断、损坏、越界可被机械判定，帮助 PM 安全收件。

## 边界（必须声明）

- **不替代** PR 审查/验收，**不证明**来源可信或提供任何签名；只保证"传输出错可检测"。
- 纯标准库；不联网、不执行 Git、不读取凭证、不删除任何既有文件。
- manifest 只含固定字段，不捕获环境信息、不接受任意额外 metadata。

## 固定协议限制

| 项 | 值 |
|------|------|
| chunk 原始载荷 | 1000 字节（base64 后约 1368 字符） |
| 单文件上限 | 8 MiB（8388608 字节） |
| 总量上限 | 16 MiB（16777216 字节） |
| 文件数 | 1..5 |
| bundle 文件 | UTF-8 JSON，≤ 64 MiB |
| 退出码 | 0 成功；1 拒绝/校验失败；2 用法错误 |

## bundle 格式

bundle 是一个 UTF-8 JSON 文件。三层对象的键集**精确固定**：多余键、缺失键、重复键（duplicate JSON key）一律拒绝。

```json
{
  "schema": "zcode-gui-artifacts/v1",
  "task_id": "TASK-…",
  "session_id": "<会话ID>",
  "branch": "feat/…",
  "base": "<40位小写hex>",
  "head": "<40位小写hex>",
  "chunk_size": 1000,
  "files": [
    {
      "path": "delivery.bundle",
      "size": 19231,
      "sha256": "<64位小写hex>",
      "chunks": [
        {"index": 0, "offset": 0, "length": 1000, "base64": "…"},
        {"index": 1, "offset": 1000, "length": 1000, "base64": "…"}
      ]
    }
  ]
}
```

约定：`index` 从 0 连续递增；`offset` 必须等于 `index * chunk_size`（即连续、无重复、无空洞）；非末尾 chunk 长度恒为 1000，末尾 chunk 长度等于剩余字节数；0 字节文件的 `chunks` 为空数组。

## 用法

```bash
# 打包（输出必须是不存在的新文件；整包写入文件，不刷 stdout，仅输出一行摘要）
python3 scripts/zcode-gui-artifacts.py pack \
  --source /path/to/card/root \
  --task TASK-… --session <会话ID> --branch feat/… \
  --base <40hex> --head <40hex> \
  --output /path/to/delivery.bundle \
  delivery.bundle delivery.json pr-body.md

# 收件（先完整验证，再写入不存在的新目标目录）
python3 scripts/zcode-gui-artifacts.py unpack \
  --bundle /path/to/delivery.bundle --target /path/to/new-dir

# 按 文件/索引 输出唯一一条有界 chunk JSON（固定键），适配 terminal 传输
python3 scripts/zcode-gui-artifacts.py emit-chunk \
  --bundle /path/to/delivery.bundle --file delivery.bundle --chunk 0
```

`emit-chunk` 输出单行 JSON，固定键为：`schema`、`bundle_sha256`（bundle 文件整体的 SHA256）、`file`、`index`、`offset`、`length`、`base64`。接收方据此可判定缺行（index 断档）、错位（offset 不符）、张冠李戴（bundle_sha256 不符）。

## pack 拒绝清单

- artifact 数量不在 1..5；
- 绝对路径、`..` 穿越、`.`、空路径段（`a//b`、尾斜杠）、反斜杠路径、超长路径（>1024 字符）；
- symlink（文件本身或任一父级组件；source 根本身是 symlink 也拒绝）；
- 非常规文件（目录、fifo 等）；
- 重复路径（按精确相对路径判重；不同目录下的同名文件不冲突，因 unpack 保留相对路径结构）；
- 单文件 > 8 MiB、总量 > 16 MiB；
- `--output` 已存在（含悬空 symlink）——从不覆盖；
- `--base`/`--head` 非 40 位小写 hex。

## unpack 验证顺序与失败语义

1. bundle 文件本身：存在、非常规 symlink、UTF-8、JSON 合法、无重复键；
2. manifest 顶层键集与类型（`bool` 不算 int）；
3. 逐文件：路径合法且唯一、无嵌套冲突、size/总量上限、sha256 格式；
4. 逐 chunk：键集、index 连续、offset 连续无重复、长度规则、base64 严格解码且长度一致；
5. 全部文件 SHA256 复核。

全部通过后才创建目标目录并写盘（`xb` 独占创建）。**任一步失败不写目标、不覆盖既有文件**（失败零落盘）；目标已存在或为 symlink 拒绝；目标父目录必须已存在且非 symlink。写盘阶段如遇 I/O 错误会回滚本命令在目标内创建的内容。

## 与 terminal 传输的配合

整包优先以文件传递（scp/文件共享/直接复制）。唯一通道是终端文本时，用 `emit-chunk` 逐条输出有界 chunk；接收方保存每条后，可依据 `file/index/offset/length` 与 `bundle_sha256` 人工核对完整性。**本工具当前不提供"把收到的 chunk 重新装配回 bundle"的自动 ingest**，该步骤超出本卡范围（见 pr-body 边界声明）。

## 测试

```bash
python3 skills/multi-agent-orchestration/scripts/test-zcode-gui-artifacts.py
```

覆盖：真实 CLI 二进制往返（0 字节、999/1000/1001/2000 边界、嵌套路径、确定性）、pack 阴性反例（穿越/绝对/symlink/重复/超限/不覆盖）、manifest 坏类型/重复 JSON 键/缺 chunk/offset 重复或空洞/改 digest/坏 base64/超限/目标存在/symlink/失败零落盘、emit-chunk 固定键与有界输出。
