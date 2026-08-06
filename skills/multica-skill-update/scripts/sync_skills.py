#!/usr/bin/env python3
"""
Multica Skill 同步工具 —— 维护同步清单并批量导入/更新 Multica 工作区 skill

按 config/manifest.local.json（个人同步清单）逐条执行 `multica skill import`，
把 GitHub / ClawHub / skills.sh / 本地文件 上的 skill 同步到 Multica skill 数据库。

三种模式（--mode）：
    init    初始化导入：对每条 enabled 技能执行 import；同名已存在（conflict）视为正常，
            转成"已存在，跳过"提示，不报错退出。
    update  更新刷新：与 init 基本一致，但 on_conflict 按清单里的策略执行。
            overwrite 刷新内容（保留 skill ID 与 agent 绑定，需为原始创建者）；
            skip 跳过非本人创建的技能。
    plan    无副作用预览：只列出将执行的操作，不调用 import。

用法:
    python sync_skills.py --manifest config/manifest.local.json --mode init
    python sync_skills.py --mode update              # 默认读 config/manifest.local.json
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
        url         来源 URL；source=file 时为本机路径，支持三种形态：
                      - 技能目录（含符号链接）：自动打包成临时 zip 后导入
                      - .zip / .skill 归档：直接导入
                    （CLI 的 --file 只收 .skill/.zip，目录打包由本脚本处理）
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
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# App 内置 CLI 路径（darwin）
APP_MULTICA_BIN = "/Applications/Multica.app/Contents/Resources/app.asar.unpacked/resources/bin/multica"

# 打包本地技能目录时排除的噪音与工作产物目录。
# archive/output/tmp 是各技能的运行产物（如 legal-ocr 的 archive/ 达 7.6GB），
# 打进包既超服务端限制也无意义。dotfile 目录服务端本就会丢弃，本地先剔除省流量。
PACK_EXCLUDE_DIRS = {
    "__pycache__", ".git", ".venv", "node_modules", ".pytest_cache", ".mypy_cache",
    "archive", "output", "outputs", "tmp", ".cache", "dist", "build",
    ".idea", ".vscode",
}
PACK_EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".pyd", ".so", ".dylib"}
PACK_EXCLUDE_NAMES = {".DS_Store", "Thumbs.db"}

# 服务端导入限制（见内置 multica-skill-importing 技能的 source map）：
#   per-file 1 MiB / per-bundle 8 MiB / file-count 256 / upload 16 MiB(compressed)
SERVER_MAX_FILE_SIZE = 1024 * 1024
SERVER_MAX_TOTAL_SIZE = 8 * 1024 * 1024
SERVER_MAX_FILE_COUNT = 256
SERVER_MAX_UPLOAD_SIZE = 16 * 1024 * 1024

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
        tmpl = path.parent / ".." / "references" / "manifest.example.json"
        hint = f"\n    参考模板：{tmpl.resolve()}\n    或从 references/manifest.example.json 复制为 config/manifest.local.json 后填写"
        raise SyncError(f"manifest 不存在：{path}{hint}")
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


def _collect_files(real: Path) -> list[Path]:
    """遍历技能目录，剔除噪音/工作产物，返回待打包文件列表。"""
    files: list[Path] = []
    for path in real.rglob("*"):
        rel_parts = path.relative_to(real).parts
        # 目录级排除：命中黑名单，或任一层级是 dotfile 目录（服务端亦会丢弃）
        if any(p in PACK_EXCLUDE_DIRS or p.startswith(".") for p in rel_parts[:-1]):
            continue
        if path.name in PACK_EXCLUDE_NAMES or path.suffix in PACK_EXCLUDE_SUFFIXES:
            continue
        if path.is_file():
            files.append(path)
    return sorted(files)


def _precheck(real: Path, files: list[Path]) -> list[str]:
    """按服务端限制预检，返回告警列表（不阻断，仅提示）。

    服务端会丢弃 dotfiles / __MACOSX / license / 二进制资产，且支持文件
    不得名为 SKILL.md（会被静默丢弃）。这里按"服务端实际会保留的文件"估算。
    """
    kept = [
        f for f in files
        if not f.name.startswith(".")
        and "license" not in f.name.lower()
        and f.relative_to(real).as_posix() != "SKILL.md"
    ]
    warns = []
    if len(kept) > SERVER_MAX_FILE_COUNT:
        warns.append(f"文件数 {len(kept)}>{SERVER_MAX_FILE_COUNT}")
    total = sum(f.stat().st_size for f in kept)
    if total > SERVER_MAX_TOTAL_SIZE:
        warns.append(f"总体积 {total/1024/1024:.1f}MiB>8MiB")
    over = [f for f in kept if f.stat().st_size > SERVER_MAX_FILE_SIZE]
    if over:
        names = ", ".join(f.relative_to(real).as_posix() for f in over[:2])
        warns.append(f"{len(over)} 个文件>1MiB（{names}{'...' if len(over) > 2 else ''}）")
    # 支持文件重名 SKILL.md（非根级）会被服务端静默丢弃
    dropped = [f for f in files
               if f.name == "SKILL.md" and f.relative_to(real).as_posix() != "SKILL.md"]
    if dropped:
        names = ", ".join(f.relative_to(real).as_posix() for f in dropped[:2])
        warns.append(f"{len(dropped)} 个支持文件名为 SKILL.md，将被服务端静默丢弃（{names}）")
    return warns


def _pack_dir(src: Path, tmp_dir: Path) -> tuple[Path, list[str]]:
    """把本地技能目录打包成 zip（multica import --file 只收 .skill/.zip，不收目录）。

    符号链接目录同样适用：Path.resolve() 后走真实路径遍历。
    zip 内保留顶层目录名 —— 服务端会 root 到最浅的 SKILL.md，
    顶层目录名亦作为 name 兜底（frontmatter name 优先）。

    返回 (zip 路径, 服务端限制告警列表)。
    """
    real = src.resolve()
    files = _collect_files(real)
    warns = _precheck(real, files)
    zip_path = tmp_dir / f"{real.name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            zf.write(path, Path(real.name) / path.relative_to(real))
    size = zip_path.stat().st_size
    if size > SERVER_MAX_UPLOAD_SIZE:
        warns.append(f"压缩包 {size/1024/1024:.1f}MiB>16MiB 上传上限")
    return zip_path, warns


def _run(cmd: list[str], dry_run: bool) -> tuple[int, str]:
    """执行 multica 命令；dry_run 只打印。返回 (exit_code, stdout)。"""
    if dry_run:
        print(f"  [dry-run] {' '.join(cmd)}")
        return 0, ""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        # 冲突/失败时 CLI 非零退出，结构化信封可能落在 stderr，合并后再解析
        out = proc.stdout if proc.stdout.strip() else proc.stderr
        return proc.returncode, out
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

    print(f"  - {name} [{source}] → import --on-conflict {strategy}")

    # import 参数：--url 与 --file 互斥
    tmp_dir_obj = None
    if source == "file":
        flag = "--file"
        local = Path(url).expanduser()
        if not local.exists():
            _failed += 1
            print(f"  - {name}: 本地路径不存在 {local}，失败")
            return
        if local.is_dir():
            # CLI 只接受 .skill/.zip 归档，目录先打包成临时 zip
            if dry_run:
                value = f"<临时打包 {local.name}.zip>"
            else:
                tmp_dir_obj = tempfile.TemporaryDirectory(prefix="multica-pack-")
                value, warns = _pack_dir(local, Path(tmp_dir_obj.name))
                for w in warns:
                    print(f"    ⚠️  {w}")
                value = str(value)
        else:
            if local.suffix not in (".skill", ".zip"):
                _failed += 1
                print(f"  - {name}: 本地文件需为 .skill/.zip（当前 {local.suffix or '无后缀'}），失败")
                return
            value = str(local)
    else:
        flag = "--url"
        value = url

    try:
        cmd = ctx.base_args() + [
            "skill", "import", flag, value,
            "--on-conflict", strategy, "--output", "json",
        ]
        code, out = _run(cmd, dry_run)
    finally:
        if tmp_dir_obj is not None:
            tmp_dir_obj.cleanup()
    if dry_run:
        return

    _handle_result(name, strategy, code, out)


def _handle_result(name: str, strategy: str, code: int, out: str) -> None:
    """按 Multica 结构化导入结果信封判定，而非猜测 exit code / 字符串。

    信封（见内置 multica-skill-importing 技能）：
        {"status": "created|updated|conflict|skipped|failed",
         "reason": "...", "skill": {...},
         "existing_skill": {"id","name","can_overwrite"}}
    旧版服务端可能只回 409 + {"error", "existing_skill"}，CLI 已归一化为
    status=conflict；再旧的只回纯字符串，这里兜底按字符串判断。
    """
    global _imported_created, _imported_updated, _conflict_existed
    global _skipped_not_creator, _skipped_disabled, _failed

    envelope = _parse_envelope(out)
    status = envelope.get("status") if envelope else None
    reason = (envelope or {}).get("reason") or ""
    skill = (envelope or {}).get("skill") or {}
    existing = (envelope or {}).get("existing_skill") or {}
    sid = skill.get("id") or existing.get("id") or ""
    files = skill.get("files")
    detail = f" id={sid[:8]}" if sid else ""
    if isinstance(files, list):
        detail += f" files={len(files)}"

    if status == "created":
        _imported_created += 1
        print(f"    ✅ created{detail}")
        return
    if status == "updated":
        _imported_updated += 1
        print(f"    🔄 updated{detail}（保留 ID 与 agent 绑定）")
        return
    if status == "skipped":
        _skipped_not_creator += 1
        print(f"    ⏭️  skipped：已存在，策略 skip{detail}")
        return
    if status == "conflict":
        _conflict_existed += 1
        can = existing.get("can_overwrite")
        hint = "，可改用 on_conflict=overwrite" if can else "，非本人创建，无法 overwrite"
        print(f"    ⚠️  conflict：同名已存在{detail}{hint}")
        return
    if status == "failed":
        _failed += 1
        # overwrite 对非创建者会返回 failed，属预期内的权限限制
        if strategy == "overwrite" and existing and not existing.get("can_overwrite", True):
            _failed -= 1
            _skipped_not_creator += 1
            print(f"    ⏭️  overwrite 被拒：非本人创建的技能{detail}")
            return
        print(f"    ❌ failed：{reason or out.strip()[:160]}")
        return

    # 无结构化信封：回退到 exit code + 字符串
    if code == 0:
        _imported_created += 1
        print(f"    ✅ imported（无结构化 status，按 exit=0 计）")
        return
    low = out.lower()
    if "already exists" in low or "conflict" in low or "existing" in low:
        _conflict_existed += 1
        print(f"    ⚠️  同名已存在（旧版服务端响应）")
        return
    _failed += 1
    print(f"    ❌ 失败（exit={code}）: {out.strip()[:200]}")


def _parse_envelope(out: str) -> Optional[dict[str, Any]]:
    """从 CLI stdout 中提取结构化导入结果 JSON；失败返回 None。"""
    text = out.strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # 输出可能混有日志行，取最后一个完整 JSON 对象
        start = text.find("{")
        if start < 0:
            return None
        try:
            data = json.loads(text[start:])
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


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
                        help="清单路径（默认 <skill根>/config/manifest.local.json）")
    parser.add_argument("--mode", default="update", choices=["init", "update", "plan"],
                        help="init=初始化导入 / update=更新刷新 / plan=无副作用预览")
    parser.add_argument("--category", default=None,
                        help="只同步指定分类的技能（按清单里每条的 category 字段过滤；"
                             "如 development / legal-document / content-writing；留空同步全部）")
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
        else skill_root / "config" / "manifest.local.json"

    try:
        manifest = _load_manifest(manifest_path)
    except SyncError as exc:
        _err(str(exc))
        return 2

    items = manifest.get("skills", [])
    if args.category:
        items = [s for s in items if s.get("category") == args.category]
        print(f"清单: {manifest_path}（按 category={args.category} 过滤，{len(items)} 条）")
    else:
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
