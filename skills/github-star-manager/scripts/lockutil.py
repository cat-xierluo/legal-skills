"""跨进程写锁（R3：上游终审计 F07 返修——双仓共同写入协议）

背景：技能（save_latest / generate_dashboard / quick_export）与 star-board 插件
（sync / 翻译回写 / unstar）会写同一 output 目录下的 original_latest.json 与
data.js。此前防线（原子替换 + mtime 复检）仍有 TOCTOU 竞隙：技能在插件「复检通过」
与「提交」之间写入时，插件的旧读会覆盖技能的新增。

协议（两仓共同遵守）：
- 锁文件：<output>/.gsm-write.lock（与数据文件同目录，两侧都能定位）
- 锁类型：fcntl.flock(LOCK_EX) 排他；读-改-写全程持锁，不留复检窗口
- 超时：默认 10s，未取得锁抛 LockUnavailable（调用方必须 fail-closed，不无锁写）
- 无 fcntl 平台：默认拒绝写入（fail-closed）；确需降级设 GSM_ALLOW_UNLOCKED_WRITE=1
- 平台：Windows 无 fcntl 时降级为无锁（记录一次警告），行为回退到原子写+mtime 复检

本模块只提供锁原语，不碰数据格式；插件侧 plugin_api 使用同一锁文件与同名协议。
"""

import os
import sys
import time
import contextlib
from pathlib import Path
from typing import Optional

try:
    import fcntl
    HAS_FLOCK = True
except ImportError:  # Windows
    fcntl = None
    HAS_FLOCK = False

LOCK_FILENAME = ".gsm-write.lock"
_DEFAULT_TIMEOUT = 10.0
_warned_no_flock = False


class LockUnavailable(RuntimeError):
    """R6/J1b：跨进程写锁不可用（超时/无 fcntl/打不开锁文件）。

    继承自 RuntimeError；调用方必须 fail-closed（拒绝写入、保留旧数据、返回
    非成功），**不得**退回无锁的破坏性成功路径。环境变量
    GSM_ALLOW_UNLOCKED_WRITE=1 显式声明本机无 fcntl 时接受降级（默认拒绝）。
    """


def lock_path(output_dir: Path) -> Path:
    """锁文件路径（与数据文件同目录；两仓共同约定）。"""
    return Path(output_dir) / LOCK_FILENAME


@contextlib.contextmanager
def write_lock(output_dir: Path, timeout: Optional[float] = None):
    """持有写锁执行临界区（读-改-写全程）。

    Args:
        output_dir: 数据目录（含 original_latest.json / data.js）
        timeout: 获取锁的最长等待秒数；None → 运行时取 _DEFAULT_TIMEOUT（可被测试 patch）

    Raises:
        LockUnavailable: 未取得锁——超时/无 fcntl 且未显式放行/锁文件打不开。
            调用方必须 fail-closed（不写入）。
    """
    global _warned_no_flock
    if timeout is None:
        timeout = _DEFAULT_TIMEOUT
    # R9/G3 收窄：该 flag 仅放行"平台无 fcntl"——上游实测旧实现连活锁都能绕。
    # 锁被另一进程持有时（超时/打不开），**无论 flag 与否一律 fail-closed**。
    allow_unlocked = os.environ.get("GSM_ALLOW_UNLOCKED_WRITE") == "1"
    if not HAS_FLOCK:
        if allow_unlocked:
            yield False
            return
        raise LockUnavailable(
            "平台无 fcntl，无法保证跨进程互斥"
            "（确需降级请设 GSM_ALLOW_UNLOCKED_WRITE=1，仅限无 fcntl 平台）")

    path = lock_path(output_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(path), os.O_CREAT | os.O_RDWR, 0o644)
    except OSError as e:
        raise LockUnavailable(f"无法打开锁文件 {path}: {e}") from e
    deadline = time.monotonic() + max(0.0, timeout)
    acquired = False
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise LockUnavailable(
                        f"等待写锁超时（{timeout}s）：{path}——另一写者持有中，"
                        f"已拒绝无锁写入（GSM_ALLOW_UNLOCKED_WRITE 不放行活锁）")
                time.sleep(0.05)
        yield True
    finally:
        if acquired:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
        os.close(fd)
