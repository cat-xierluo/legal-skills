# 核心 Skill 配置

`config/core_skills.yaml` 是本地个人配置，不入 Git（入 Git 的是模板 `config/core_skills.example.yaml`，复制后填写）。它是重点关注配置，不是全仓 Skill 清单；自动 inventory 才是候选全集。文件缺失时 inventory 使用默认 agent 目录来源、重点覆盖为空，功能可正常运行。

## 最小结构

```yaml
version: "2.0"
last_updated: "YYYY-MM-DD"

skill_sources:
  private-skills: <private-skills-root>
  legal-skills: <legal-skills-root>

core_skills:
  - id: example-skill
    display_name: 示例 Skill
    source: private-skills
    function: 说明输入、动作和产出
    domain_keywords:
      - 领域词
    priority: high
    last_reviewed: YYYY-MM-DD
```
## 字段约束

- `skill_sources`：提供 inventory 扫描根；不要给同一真实目录配置多个别名。
- `core_skills[].id`：与目标目录或 frontmatter `name` 保持稳定映射。
- `source`：引用 `skill_sources` 中的键。
- 目标 Skill 的版本与内容哈希只从 runtime inventory 读取；不要在重点配置中复制 `version` 或 `upgrade_target`，避免长期漂移。
- `function`：用一句可验证描述说明能力，不复制整份正文。
- `domain_keywords`：用于候选路由和聚类加权，不单独决定提案接受。
- `priority`：只影响审阅优先级，不把非核心 Skill 排除出候选全集。
- `references`：只记录目标 Skill 内部的相对路径。

## 输出路径

`output_paths` 只表达 `<data-root>` 下的逻辑位置。实际根由 `scripts/self_evolve_paths.py` 统一解析；不要在业务脚本中重复拼接源码树路径。

修改配置后运行：

```bash
python3 scripts/refresh_skill_inventory.py
python3 scripts/scheduler_run.py --validate-config --json
```
