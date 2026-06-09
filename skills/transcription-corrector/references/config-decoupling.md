# Config Decoupling

> 本文件聚焦**配置示例 / 配置解耦原则**——是 skill 公开化时需要满足的评价规范的一部分，与工作流无关。
> 概述 / 适用边界见 [scope.md](scope.md)。
> 工作流判断准则见 [correction_patterns.md](correction_patterns.md)。
> 首次使用流程见 [first_use.md](first_use.md)。

## 配置示例

**完整公开模板**：见 [../config/user_dictionary.example.yaml](../config/user_dictionary.example.yaml)。包含常见技术名词（行业公认的产品 / 平台 / 格式 / 缩写）与常见法律术语（法律行业通用术语）。

**最小词典**（3 项起步，新用户复制后可立即使用）：

```yaml
version: 1
terms:
  - "WorkBuddy"
  - "Claude Code"
  - "Codex"
```

**进阶个性化**：复制 example.yaml 为本地 user_dictionary.yaml 后，**追加**个人项到 `terms` 列表（不要覆盖 example.yaml，否则 git 同步时会丢你的本地项）：

```yaml
version: 1
terms:
  # 通用项（来自 example.yaml，跨用户通用）
  - "WorkBuddy"
  - "Claude Code"

  # 个人工作栈（仅本机，git ignore）
  - "<你的工具栈 1>"
  - "<你的工具栈 2>"

  # 自定义 skill 名 / 项目编号
  - "<你的项目名 / 编号>"

  # 个人身份（仅本机，git ignore）
  - "<你自己的姓名>"
  - "<你的律所全称>"
  - "<你的客户代号>"
```

**进阶**：在多个场景间共用一份词典，可把本 skill 的 `config/user_dictionary.yaml` 软链到统一位置（多设备 / 多入口共用）。

## 配置解耦原则

**核心约定**：

- 模板文件命名 `*.example.*` → 提交
- 实际配置 `user_dictionary.yaml` → 不入仓（被 `.gitignore` 覆盖）
- 真实配置路径下不应有硬编码 API keys、Token、客户代号等敏感数据

本 skill 面向公开发布时，配置需要严格解耦：

| 位置 | 性质 | 是否入仓 |
|---|---|---|
| `config/user_dictionary.example.yaml` | 公开模板（常见技术名词 + 常见法律术语，跨用户通用） | ✅ 提交 |
| `config/user_dictionary.example.yaml` 同目录 `*.example.*` 模式 | 公开模板 | ✅ 提交 |
| `config/user_dictionary.yaml` | 本地个性化配置（个人人名、律所、客户、自家业务术语） | ❌ git ignore（项目根 `.gitignore` 模式 `**/config/*.yaml` + `!**/config/*.example.yaml`） |
| `references/*.md` | 通用判断准则/知识 | ✅ 提交 |
| `archive/...` | 校对产物（含原始内容快照） | ❌ git ignore（项目根 `.gitignore` 已覆盖） |

**"换另一个用户 clone 这个仓库，他需要这一项吗？"**——判定标准：

| 答案 | 写到哪里 |
|---|---|
| 需要（行业公认的技术名词 / 法律术语，跨用户都用） | `config/user_dictionary.example.yaml` |
| 不需要（个人工作栈 / 律所名 / 客户代号 / 私有项目名） | 本地 `user_dictionary.yaml` |

**`example.yaml` 当前的收纳范围**：

- ✅ 常见技术名词：行业公认的产品 / 平台 / 格式 / 缩写（ASR 容易听错）
- ✅ 常见法律术语：法律行业通用术语（ASR 容易听错为同音字 / 形近字）
- ❌ 个人工作栈工具：仅本机使用的特定技术栈产品（即使"行业"可能认识，归"个人工作栈"更准确）
- ❌ 个人身份：人名、律所名、客户代号
- ❌ 极通用词：法律、法院、律师、合同（避免触发过度替换风险）
