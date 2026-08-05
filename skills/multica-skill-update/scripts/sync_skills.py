#!/usr/bin/env python3
"""
Multica Skill 同步工具 —— 维护同步清单并批量导入/更新 Multica 工作区 skill

按 manifest.json（清单）逐条执行 `multica skill import`，把 GitHub / ClawHub /
skills.sh / 本地文件 上的 skill 同步到 Multica skill 数据库。

三种模式（--mode）：
    init    初始化导入：对每条 enabled 技能执行 import；同名已存在（conflict）视为正常，
            转成"已存在，跳过"提示，不报错退出。
    update  更新刷新：与 init 基本一致，但 on_conflict 按清单里的策略执行。
            overwrite 刷新内容（保留 skill ID 与 agent 绑定，需为原始创建者）；
            skip 跳过非本人创建的技能。
    plan    无副作用预览：只列出将执行的操作，不调用 import。

用法:
    python sync_skills.py --manifest manifest.json --mode init
    python sync_skills.py --mode update              # 默认读 skill 根目录 manifest.json
    python sync_skills.py --mode plan                # 预览
    python sync_skills.py --dry-run                  # 打印命令但不执行

连接参数（真实调用时通常需要）:
    --multica-bin       multica CLI 路径。默认自动探测：
                        1) PATH 中的 multica
                        2) Multica 桌面 App 内置 CLI
                        （/Applications/Multica.app/Contents/Resources/app.asar.unpacked/resources/bin/multica）
    --profile           Multica profile 名（如 desktop-api.multica.ai）。
                        CLI 默认用 default profile 会报 "No server configured"，
                        需指向 App 运行时用的 profile。
    --workspace-id      Workspace ID（skill list 等要求）；可用
                        `multica --profile <p> workspace list --output json` 查询。

清单字段:
    version      清单格式版本（当前 1）
    skills[]:
        name        技能名（仅作报告标识）
        source      github | clawhub | skills.sh | file（决定 URL 形态）
        url         来源 URL；source=file 时改为本机路径
        on_conflict fail(默认) | overwrite | rename | skip
        enabled     false 时跳过该条目

依赖: multica CLI，Python 标准库。
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# App 内置 CLI 路径（darwin）
APP_MULTICA_BIN = "/Applications/Multica.app/Contents/Resources/app.asar.unpacked/resources/bin/multica"

# 报告统计
_imported_created = 0
_imported_updated = 0
_conflict_existed = 0
_skipped_not_creator = 0
_skipped_disabled = 0
_failed = 0


class SyncError(RuntimeError):
    pass


@dataclass
class CliContext:
    """multica CLI 调用上下文。"""
    bin: str = "multica"
    profile: Optional[str] = None
    workspace_id: Optional[str] = None

    def base_args(self) -> list[str]:
        args = [self.bin]
        if self.profile:
            args += ["--profile", self.profile]
        if self.workspace_id:
            args += ["--workspace-id", self.workspace_id]
        return args


def _err(msg: str) -> None:
    print(f"ERROR {msg}", file=sys.stderr)


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SyncError(f"manifest 不存在：{path}")
    except json.JSONDecodeError as exc:
        raise SyncError(f"manifest JSON 无效：{path}:{exc.lineno}:{exc.colno} {exc.msg}")
    if not isinstance(data, dict) or not isinstance(data.get("skills"), list):
        raise SyncError(f"manifest 结构错误：{path}，需要 {{'version': 1, 'skills': [...]}}")
    return data


def _resolve_cli(args_bin: Optional[str]) -> str:
    """确定 multica CLI 路径：优先 --multica-bin，其次 PATH，其次 App 内置。"""
    if args_bin:
        p = Path(args_bin).expanduser()
        if p.exists():
            return str(p)
        _err(f"--multica-bin 指定的路径不存在：{p}")
        raise SystemExit(2)
    if shutil.which("multica"):
        return "multica"
    if Path(APP_MULTICA_BIN).exists():
        return APP_MULTICA_BIN
    print(
        f"❌ 未找到 multica CLI。\n"
        f"   安装：curl -fsSL https://raw.githubusercontent.com/multica-ai/multica/main/scripts/install.sh | bash\n"
        f"   或：brew install multica-ai/tap/multica\n"
        f"   本机也可直接用 App 内置：{APP_MULTICA_BIN}\n"
        f"   验证：multica version",
        file=sys.stderr,
    )
    raise SystemExit(2)


def _run(cmd: list[str], dry_run: bool) -> tuple[int, str]:
    """执行 multica 命令；dry_run 只打印。返回 (exit_code, stdout)。"""
    if dry_run:
        print(f"  [dry-run] {' '.join(cmd)}")
        return 0, ""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return proc.returncode, proc.stdout
    except subprocess.TimeoutExpired:
        return 124, ""
    except FileNotFoundError:
        return 127, ""


def _check_connection(ctx: CliContext) -> bool:
    """验证 CLI 能连上 server（有 server/token 配置）。"""
    cmd = ctx.base_args() + ["workspace", "list", "--output", "json"]
    code, out = _run(cmd, dry_run=False)
    if code != 0 or "No server configured" in out:
        print(
            f"❌ multica CLI 未连接 server（{cmd} 失败）。\n"
            f"   若使用 App 内置 CLI 或默认 profile，需加 --profile 指向 App 使用的 profile"
            f"（如 desktop-api.multica.ai），并指定 --workspace-id。\n"
            f"   查看 profile: ls ~/.multica/profiles/\n"
            f"   查 workspace: multica --profile <p> workspace list --output json",
            file=sys.stderr,
        )
        return False
    return True


def _import_one(item: dict[str, Any], ctx: CliContext, dry_run: bool) -> None:
    """对单条 enabled 技能执行 import（或 plan/dry-run 预览）。"""
    global _imported_created, _imported_updated, _conflict_existed
    global _skipped_not_creator, _skipped_disabled, _failed

    name = item.get("name", "(未命名)")
    source = item.get("source", "")
    url = item.get("url", "")
    strategy = item.get("on_conflict", "fail")
    enabled = item.get("enabled", True)

    if not enabled:
        _skipped_disabled += 1
        print(f"  - {name}: 已停用（enabled=false），跳过")
        return
    if not url:
        _failed += 1
        print(f"  - {name}: 缺少 url，失败")
        return
    if strategy not in ("fail", "overwrite", "rename", "skip"):
        _failed += 1
        print(f"  - {name}: 非法 on_conflict={strategy!r}（可选 fail/overwrite/rename/skip），失败")
        return

    # import 参数：--url 与 --file 互斥
    if source == "file":
        flag = "--file"
        value = url
    else:
        flag = "--url"
        value = url

    cmd = ctx.base_args() + [
        "skill", "import", flag, value,
        "--on-conflict", strategy, "--output", "json",
    ]
    print(f"  - {name} [{source}] → import --on-conflict {strategy}")
    code, out = _run(cmd, dry_run)
    if dry_run:
        return

    if code == 0:
        _imported_created += 1
        print(f"    ✅ imported (created)")
        return

    # 非零退出：解析输出判断是否"同名已存在"等正常情况
    low = (out + "").lower()
    if "already exists" in low or "conflict" in low or "existing" in low:
        if strategy == "skip":
            _skipped_not_creator += 1
            print(f"    ⏭️  已存在且策略为 skip，跳过")
        elif strategy == "overwrite":
            # overwrite 理论上不冲突；失败通常是"非创建者"
            _skipped_not_creator += 1
            print(f"    ⏭️  overwrite 失败（可能非本人创建，multica 拒绝），跳过")
        else:
            _conflict_existed += 1
            print(f"    ⏭️  已存在（conflict），按提示跳过")
        return

    _failed += 1
    print(f"    ❌ 失败（exit={code}）: {out.strip()[:200]}")


def _report() -> None:
    print("\n=== 同步报告 ===")
    print(f"imported: {_imported_created + _imported_updated} "
          f"(created {_imported_created}, updated {_imported_updated})")
    print(f"conflict(existed): {_conflict_existed}")
    print(f"skipped: {_skipped_not_creator + _skipped_disabled} "
          f"(not creator {_skipped_not_creator}, disabled {_skipped_disabled})")
    print(f"failed: {_failed}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sync_skills.py", description="Multica Skill 同步工具")
    parser.add_argument("--manifest", default=None,
                        help="清单路径（默认 <skill根>/manifest.json）")
    parser.add_argument("--mode", default="update", choices=["init", "update", "plan"],
                        help="init=初始化导入 / update=更新刷新 / plan=无副作用预览")
    parser.add_argument("--dry-run", action="store_true", help="打印命令但不执行")
    parser.add_argument("--multica-bin", default=None,
                        help="multica CLI 路径（默认自动探测 PATH 或 App 内置）")
    parser.add_argument("--profile", default=None,
                        help="Multica profile 名（如 desktop-api.multica.ai）")
    parser.add_argument("--workspace-id", default=None,
                        help="Workspace ID（skill 命令需要）")
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))

    # 定位 skill 根目录（本脚本位于 <skill根>/scripts/）
    skill_root = Path(__file__).resolve().parent.parent
    manifest_path = Path(args.manifest).expanduser().resolve() if args.manifest \
        else skill_root / "manifest.json"

    try:
        manifest = _load_manifest(manifest_path)
    except SyncError as exc:
        _err(str(exc))
        return 2

    items = manifest.get("skills", [])
    print(f"清单: {manifest_path}（{len(items)} 条）")
    print(f"模式: {args.mode}")

    ctx = CliContext(
        bin=_resolve_cli(args.multica_bin),
        profile=args.profile,
        workspace_id=args.workspace_id,
    )
    print(f"multica: {ctx.bin}" + (f" (profile={ctx.profile})" if ctx.profile else ""))

    if args.mode == "plan":
        print("plan 模式：仅预览，不调用 import\n")
        for item in items:
            _import_one(item, ctx, dry_run=True)
        print("\n（plan 结束，未执行任何 import）")
        return 0

    # init/update：验证连接
    if not args.dry_run:
        if not _check_connection(ctx):
            return 2

    for item in items:
        _import_one(item, ctx, args.dry_run)

    _report()

    # 有失败时退出码非零，便于调用方（autopilot/CI）感知
    return 1 if _failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
