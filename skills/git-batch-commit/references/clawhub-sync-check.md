# ClawHub 同步检查（工作流第5步）

> **核心规则：仅当项目目录下存在 `skills/clawhub-sync/` 时才执行——不存在则静默跳过，不输出任何提示。**

完成 Git 提交后，执行以下检查。

## 触发条件

完成提交后，依次执行以下**三类检测**。任一命中即提示用户是否同步。

### 检测 A：已有技能版本升级

全部满足时触发：

1. **本地存在 clawhub-sync 技能**
   - 检查 `skills/clawhub-sync/` 目录是否存在
   - **不存在则静默跳过，不提示用户**

2. **提交涉及 skills 目录**
   - 提交的文件中包含 `skills/<skill-name>/` 下的文件

3. **版本号有更新**
   - 读取 `skills/<skill-name>/SKILL.md` 的 frontmatter 中的 `version` 字段
   - 比较 `skills/clawhub-sync/config/sync-records.yaml` 中记录的版本
   - 如果新版本 > 已记录版本（或记录中无版本），则需要同步

4. **在白名单中**
   - 检查 `skills/clawhub-sync/config/sync-allowlist.yaml`
   - skill 必须在白名单中（未被 `#` 注释）

### 检测 B：新增 MIT 技能首次同步

当提交新增了 `skills/<skill-name>/` 目录时触发：

1. **识别新增技能**：检查提交中是否有 `skills/<skill-name>/SKILL.md` 为新文件（untracked → committed）

2. **许可证为 MIT**：读取新技能 `SKILL.md` frontmatter 中的 `license` 字段，判断是否为 MIT

3. **未在白名单中**：`sync-allowlist.yaml` 中无此 skill 的条目（无论是否被注释）

4. **未在同步记录中**：`sync-records.yaml` 中无此 skill 的条目

满足全部条件时，向用户提示：
```
🆕 发现新增 MIT 技能：<skill-name>
该技能尚未加入 ClawHub 同步白名单。是否将其加入白名单并同步到 ClawHub？

选项：
  y - 加入白名单并同步
  n - 跳过，暂不发布
  s - 加入白名单但暂不同步
```

用户选择 `y` 时：
- 在 `sync-allowlist.yaml` 中添加该 skill（添加到对应分类区域）
- 执行 prepare-publish → publish → 更新 sync-records 流程
- **注意**：发布前检查临时目录，确保不含 `.env`、密钥等敏感文件

用户选择 `s` 时：
- 仅在 `sync-allowlist.yaml` 中添加该 skill（被注释），下次版本更新时再同步

### 检测 C：白名单新增但未同步

当白名单中有未被注释的 skill，但 `sync-records.yaml` 中没有对应记录时：

1. 遍历 `sync-allowlist.yaml` 中未被注释的 skill
2. 检查 `sync-records.yaml` 中是否有该 skill 的记录
3. 如果白名单有但记录中没有，且 `SKILL.md` 存在，提示用户执行首次同步

## 执行步骤

对于每个需要同步的 skill，按照 `clawhub-sync` 的"单个 Skill 同步工作流"执行：

**步骤 1：准备发布目录**
```bash
bash skills/clawhub-sync/scripts/prepare-publish.sh skills/<skill-name>
```

**步骤 2：执行发布（使用 publish 命令）**
```bash
clawhub publish /tmp/clawhub-publish-<skill-name> \
  --slug <skill-name> \
  --name "<Display Name>" \
  --version "<新版本号>" \
  --changelog "<变更说明>"
```

> **⚠️ 必须指定 --slug 和 --name**
> - 临时目录名可能包含前缀，使用 `--slug` 确保正确的 skill 标识符
> - 使用 `--name` 确保 ClawHub 上显示正确的名称

> **为什么用 `publish` 而不是 `sync`？**
> - `clawhub sync` 会扫描所有目录的 skills，可能遇到 slug 冲突
> - `clawhub publish <path>` 只发布指定路径的单个 skill，更精确

**步骤 3：更新同步记录**

更新 `skills/clawhub-sync/config/sync-records.yaml`：
- 更新 `version` 为新版本号
- 更新 `last_sync` 为当前时间
- 更新 `git_hash` 为当前 commit hash
- 更新 `status` 为 `synced`
- 添加 `url` 和 `publish_id`（从命令输出获取）

## 失败处理

- 同步失败时仅显示警告信息
- 不影响 Git 提交结果
- 继续处理其他 skills

## 版本比较逻辑

```
new_version = SKILL.md frontmatter 中的 version（如 "1.2.0"）
recorded_version = sync-records.yaml 中记录的版本（如 "1.1.0"）

if new_version > recorded_version:
    执行同步
```

版本号按语义化版本规则比较（major.minor.patch）。

## 示例场景

| 场景 | 版本变化 | 白名单 | 同步记录 | 结果 |
|------|----------|--------|----------|------|
| 版本升级（检测A） | "1.0.0" → "1.1.0" | 在白名单 | 有记录 | ✅ 执行同步 |
| 无版本变化（检测A） | "1.1.0" → "1.1.0" | 在白名单 | 有记录 | ❌ 跳过 |
| 不在白名单（检测A） | 任意 | 被注释 | - | ❌ 跳过 |
| 白名单内首次发布（检测A/C） | "1.0.0" | 在白名单 | 无记录 | ✅ 执行同步 |
| 新增 MIT 技能（检测B） | "0.1.0" | 无条目 | 无记录 | ✅ 提示用户选择 |
| 新增 CC 技能（检测B） | "0.1.0" | 无条目 | 无记录 | ❌ 非 MIT 跳过 |
| clawhub-sync 不存在 | - | - | - | ❌ 静默跳过整个工作流 |
