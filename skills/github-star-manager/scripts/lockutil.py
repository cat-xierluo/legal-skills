"""跨进程写锁（R3：上游终审计 F07 返修——双仓共同写入协议）

背景：技能（save_latest / generate_dashboard / quick_export）与 star-board 插件
（sync / 翻译回写 / unstar）会写同一 output 目录下的 original_latest.json 与
data.js。此前防线（原子替换 + mtime 复检）仍有 TOCTOU 竞隙：技能在插件「复检通过」
与「提交」之间写入时，插件的旧读会覆盖技能的新增。

协议（两仓共同遵守）：
- 锁文件：<output>/.gsm-write.lock（与数据文件同目录，两侧都能定位）
- 锁类型：fcntl.flock(LOCK_EX) 排他；读-改-写全程持锁，不留复检窗口
- 超时：默认 10s，超时抛 TimeoutError（调用方决定降级或报错）
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


def lock_path(output_dir: Path) -> Path:
    """锁文件路径（与数据文件同目录；两仓共同约定）。"""
    return Path(output_dir) / LOCK_FILENAME


@contextlib.contextmanager
def write_lock(output_dir: Path, timeout: float = _DEFAULT_TIMEOUT):
    """持有写锁执行临界区（读-改-写全程）。

    Args:
        output_dir: 数据目录（含 original_latest.json / data.js）
        timeout: 获取锁的最长等待秒数

    Raises:
        TimeoutError: 超时未取得锁（调用方按业务决定重试或降级）
    """
    global _warned_no_flock
    if not HAS_FLOCK:
        if not _warned_no_flock:
            print("⚠️ 当前平台无 fcntl：跨进程写锁降级为原子写+mtime 复检", file=sys.stderr)
            _warned_no_flock = True
        yield False
        return

    path = lock_path(output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_CREAT | os.O_RDWR, 0o644)
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
                    raise TimeoutError(
                        f"等待写锁超时（{timeout}s）：{path}——另一写者持有中")
                time.sleep(0.05)
        yield True
    finally:
        if acquired:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
        os.close(fd)
