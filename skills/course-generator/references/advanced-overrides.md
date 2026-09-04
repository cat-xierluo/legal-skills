# 高级章节上限覆盖

仅在用户明确要求课程超过 8 章时读取本文件。普通生成流程不得加载、猜测或主动建议本覆盖参数。

先把用户明确要求的章节上限记为同一个整数，再在计划与最终验收中使用相同值：

```bash
python3 scripts/ledger_tool.py plan \
  <课程目录>/course-manifest.json \
  <临时目录>/chapter-plan.json \
  --max-chapters <用户明确要求的上限>

bash scripts/verify.sh \
  <课程目录> \
  --source-root <单个来源文件或来源根目录> \
  --max-chapters <同一上限>
```

本覆盖只放宽章节数量，不放宽素材绑定、章节深度、图片、权威修正、正文书面化或审计分离等其他门禁。若用户只说“内容要详尽”而未明确要求超过 8 章，仍使用默认上限，通过合并薄章、增加章内展开保留内容。
