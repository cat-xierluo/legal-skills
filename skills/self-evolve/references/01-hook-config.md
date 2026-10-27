# 旧 SessionEnd 残留处理

本文件只说明 v0.7.0 对旧配置的兼容处理。现役架构由外部 Cron 驱动，旧 SessionEnd 流程不得作为运行入口。

## 状态检查

```bash
python3 scripts/legacy_hook.py status --json
```

检查结果应区分：

- 是否发现 Self Evolve 或旧名称相关残留；
- 命中位置与数量；
- 其他项目配置是否存在；
- 当前操作是否只读。

状态检查不得改写设置文件。

## 清理预览与应用

先预览：

```bash
python3 scripts/legacy_hook.py remove --json
```

确认后显式应用：

```bash
python3 scripts/legacy_hook.py remove --apply --json
```

应用时必须：

1. 先创建时间戳备份；
2. 只移除能确定属于 Self Evolve 的条目；
3. 保留其他项目的全部设置；
4. 原子写回并输出结构化结果；
5. 使用稳定文件锁并校验读取时的内容版本；设置在读取后被其他进程改动时拒绝覆盖；
6. 不创建任何新的会话结束入口。

分支代码不得自行修改全局设置。是否执行 `--apply` 由用户决定。
