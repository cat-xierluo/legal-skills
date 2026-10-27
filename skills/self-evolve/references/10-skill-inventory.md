# Skill Inventory

## 分工

| 数据 | 来源 | 用途 |
|------|------|------|
| `config/core_skills.yaml` | 人工维护 | 重点关注、关键词和优先级 |
| `runtime/skill-inventory.json` | 自动扫描 | 全部候选 Skill 的规范索引 |
| `runtime/skill-inventory.md` | 自动扫描 | 人工浏览摘要 |

`core_skills` 不是候选全集。新建、改名或不在重点列表中的 Skill 仍应进入 inventory。

## 扫描与去重

运行：

```bash
python3 scripts/refresh_skill_inventory.py
```

对每个 source 下的 Skill：

1. 找到包含 `SKILL.md` 的目录；
2. 解析 frontmatter 的 `name`、`description`、`version` 和 `license`；
3. 解析 canonical realpath；
4. 以 realpath 合并符号链接和重复 source；
5. 计算稳定 skill key 与内容指纹；
6. 以确定性顺序写出 JSON 与 Markdown。

当同一真实目录从多个 source 被发现时，保留来源别名列表，但只产生一个 inventory entry。

## 边界

- inventory 不复制 references 正文；
- inventory 不保存 portrait 或 chain graph；
- inventory 刷新不调用 LLM；
- inventory 是运行缓存，不作为人工编辑配置；
- 私有完整路径只保存在外部数据根，不进入可提交源码。

画像与链路图使用独立文件，见 `references/14-skill-portrait.md`。
