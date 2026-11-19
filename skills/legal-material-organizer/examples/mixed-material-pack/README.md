# 匿名混合材料示例

这个示例只包含虚构文本材料，用来演示目录扫描、manifest 生成和处理任务导出，不包含真实案件、真实主体或客户材料。

在 Skill 目录执行：

```bash
python3 scripts/scan_materials.py examples/mixed-material-pack/input \
  --no-write-md \
  --archive-dir /tmp/legal-material-organizer-example/archive \
  --work-dir /tmp/legal-material-organizer-example/work
manifest=$(find /tmp/legal-material-organizer-example/archive -name materials_manifest.json -print -quit)
python3 scripts/material_processing_handoff.py export \
  --manifest "$manifest"
```

`input/` 中的 `external-source.url` 是一个保留域名网页链接，模拟需要授权网页读取的材料；扫描后应导出网页捕获任务，而不是被标记为已理解。
