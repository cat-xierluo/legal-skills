# 首次使用流程

> 本文件是一次性配置引导，**不**属于工作流判断准则。
> 工作流相关的判断准则（误转写识别、口语词精简边界等）见 [correction_patterns.md](correction_patterns.md)。

## 1. 准备用户词典

**复制** `config/user_dictionary.example.yaml` 为 `config/user_dictionary.yaml`，开始维护你的本地个性化术语。

```bash
cp config/user_dictionary.example.yaml config/user_dictionary.yaml
```

**两个文件的分工**：

| 文件 | 内容 | 入仓 |
|---|---|---|
| `config/user_dictionary.example.yaml` | 公开模板：常见技术名词 + 常见法律术语 | ✅ 提交 |
| `config/user_dictionary.yaml` | 本地个性化配置：个人人名、律所、客户、自家业务术语 | ❌ git ignore（已被 `.gitignore` 覆盖） |

**判定标准**："换另一个用户 clone 这个仓库，他需要这一项吗？"

- 需要（行业公认）→ `user_dictionary.example.yaml`
- 不需要（个人化）→ 本地 `user_dictionary.yaml`

详细收纳范围见 SKILL.md "配置解耦原则"小节。

## 2. 在本地 yaml 中追加个人项

打开 `config/user_dictionary.yaml`，在 `terms` 列表末尾追加：

```yaml
terms:
  # example.yaml 已有的通用项（不要删）
  - "WorkBuddy"
  - "Claude Code"
  ...

  # 你的个人项（追加在这里）
  - "你自己的姓名"
  - "你的律所全称"
  - "你的客户代号"
  - "你的业务领域专属术语"
```

**维护原则**：

- 每次新发现 ASR 同音字 / 拼写漂移导致误转写时，把目标值追加到对应区
- 不要删除 example 里已有的通用项——这些是基础底座
- 不要为追求"用词典"而强行替换普通词

## 3. 跑一次试跑验证

准备一份 ASR 转录稿（`.md` 或 `.txt`），调用本 skill：

- 校对结果归档到 `{skill 目录}/archive/{YYYYMMDD_HHMMSS}_{原文件 basename}/`
- 源文件目录同步输出 `{原文件}_corrected.md` 易访问副本
- 校对日志在 `correction_log.md`，按"高置信替换 / 基础空白清理 / 口语词精简 / 未处理"四区分类

**首次跑推荐先观察"未处理"区**——根据实际未改的项决定是否需要：
- 补充词典项（按实战反馈追加个人术语）
- 调整 references 规则（如某些形式漂移模式未覆盖）
- 重新跑同一份稿看增量

## 4. 进阶：多用户 / 多设备共用

**软链方案**：

```bash
# 把本 skill 的真实 yaml 软链到统一位置
ln -s ~/Dropbox/dictionaries/legal_user_dictionary.yaml \
   config/user_dictionary.yaml
```

这样多个 skill / 多台设备共享同一份词典，避免在多处维护。

**注意**：软链的目标文件本身也应 git ignore（不要提交私人词典到任何仓库）。

## 5. 不该做的事

- ❌ 不要把个人项（姓名 / 律所 / 客户）追加到 `user_dictionary.example.yaml`——一旦 commit 会通过公开仓库泄露
- ❌ 不要修改 `config/.gitignore` 让真实 yaml 入仓
- ❌ 不要为了让词典项"用上"而强行替换普通词
- ❌ 不要在跑之前删 `archive/` 下历史归档——它们是校对质量的承载体
