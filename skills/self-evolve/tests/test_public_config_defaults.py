"""UP-CFG 回归：实际配置不入 Git 后的缺省与本地覆盖契约。

锁五条（DEC-053）：
1. config/data_root.yaml 缺失 → 数据根解析到平台默认；
2. config/data_root.yaml 损坏 → 导入期记录错误，任何状态写入前失败退出；
3. config/data_root.yaml 填值 → 本地覆盖生效，且环境变量优先级更高；
4. config/core_skills.yaml 缺失 → refresh_skill_inventory 用默认 agent 目录来源跑通；
5. config/core_skills.yaml 损坏 → 报可执行错误退出（rc=2），不静默丢个人来源。

子进程隔离 SELF_EVOLVE_SKILL_ROOT / SELF_EVOLVE_DATA_ROOT / HOME / XDG_STATE_HOME，
不触碰真实数据根，不依赖本机是否装有各 agent。
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
_ISOLATED_KEYS = {"SELF_EVOLVE_SKILL_ROOT", "SELF_EVOLVE_DATA_ROOT", "HOME", "XDG_STATE_HOME"}
YAML_SPEC = importlib.util.find_spec("yaml")
HAS_YAML = YAML_SPEC is not None


def _run(
    code: str,
    env: dict[str, str],
    argv: list[str] | None = None,
    *,
    with_yaml: bool = False,
) -> subprocess.CompletedProcess:
    environment = {k: v for k, v in os.environ.items() if k not in _ISOLATED_KEYS}
    environment.update(env)
    if with_yaml and YAML_SPEC and YAML_SPEC.origin:
        # Changing HOME hides a pip --user installation from the child.
        # Carry only the dependency location for tests that require it; keep
        # the separate missing-dependency probe isolated with -S.
        yaml_parent = str(Path(YAML_SPEC.origin).resolve().parent.parent)
        environment["PYTHONPATH"] = os.pathsep.join(
            filter(None, (yaml_parent, environment.get("PYTHONPATH", "")))
        )
    return subprocess.run(
        [sys.executable, "-c", code, *argv],
        capture_output=True,
        text=True,
        env=environment,
        timeout=180,
    )


def _platform_default(home: Path) -> Path:
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "maoscripts" / "state" / "self-evolve"
    return home / ".local" / "state" / "self-evolve"


class DataRootResolutionTests(unittest.TestCase):
    """数据根三层优先级的缺省/覆盖/损坏行为。"""

    def _resolve_data_root(
        self, tmp: Path, env: dict[str, str], *, with_yaml: bool = False
    ) -> Path:
        code = (
            "import sys; sys.path.insert(0, sys.argv[1]); "
            "import self_evolve_paths as p; print(p.DATA_ROOT)"
        )
        result = _run(
            code, {"HOME": str(tmp / "home"), **env}, [str(SCRIPTS_DIR)],
            with_yaml=with_yaml,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return Path(result.stdout.strip())

    def _skill_root(self, tmp: Path) -> Path:
        skill_root = tmp / "skill-root"
        (skill_root / "config").mkdir(parents=True)
        return skill_root

    def test_missing_config_uses_platform_default(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            skill_root = self._skill_root(tmp)
            value = self._resolve_data_root(
                tmp, {"SELF_EVOLVE_SKILL_ROOT": str(skill_root)}
            )
            self.assertEqual(value, _platform_default(tmp / "home"))

    def test_corrupt_config_records_error_before_writes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            skill_root = self._skill_root(tmp)
            (skill_root / "config" / "data_root.yaml").write_text(
                "{not: valid: yaml:", encoding="utf-8"
            )
            value = self._resolve_data_root(
                tmp, {"SELF_EVOLVE_SKILL_ROOT": str(skill_root)}
            )
            self.assertEqual(value, _platform_default(tmp / "home"))
            code = ("import sys; sys.path.insert(0, sys.argv[1]); "
                    "import self_evolve_paths as p; "
                    "assert p.data_root_config_error(); p.assert_runtime_ready()")
            result = _run(code, {"HOME": str(tmp / "home"),
                                 "SELF_EVOLVE_SKILL_ROOT": str(skill_root)}, [str(SCRIPTS_DIR)])
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(_platform_default(tmp / "home").exists())

    @unittest.skipUnless(HAS_YAML, "optional YAML configuration requires PyYAML")
    def test_config_value_overrides_platform_default(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            skill_root = self._skill_root(tmp)
            custom = tmp / "custom-state"
            (skill_root / "config" / "data_root.yaml").write_text(
                f'data_root: "{custom}"\n', encoding="utf-8"
            )
            value = self._resolve_data_root(
                tmp, {"SELF_EVOLVE_SKILL_ROOT": str(skill_root)}, with_yaml=True
            )
            self.assertEqual(value, custom)

    def test_env_var_beats_config_file(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            skill_root = self._skill_root(tmp)
            custom = tmp / "custom-state"
            via_env = tmp / "env-state"
            (skill_root / "config" / "data_root.yaml").write_text(
                f'data_root: "{custom}"\n', encoding="utf-8"
            )
            value = self._resolve_data_root(
                tmp,
                {
                    "SELF_EVOLVE_SKILL_ROOT": str(skill_root),
                    "SELF_EVOLVE_DATA_ROOT": str(via_env),
                },
            )
            self.assertEqual(value, via_env)


class InventoryConfigDefaultsTests(unittest.TestCase):
    """core_skills.yaml 缺失/损坏时 inventory 入口的缺省与报错行为。"""

    def _run_inventory(
        self, tmp: Path, config_path: Path, *, with_yaml: bool = False
    ) -> subprocess.CompletedProcess:
        return _run(
            "import sys; sys.path.insert(0, sys.argv[1]); sys.argv = ['refresh_skill_inventory.py', '--config', sys.argv[2]];"
            "import refresh_skill_inventory; raise SystemExit(refresh_skill_inventory.main())",
            {
                "HOME": str(tmp / "home"),
                "SELF_EVOLVE_DATA_ROOT": str(tmp / "state"),
            },
            [str(SCRIPTS_DIR), str(config_path)],
            with_yaml=with_yaml,
        )

    def test_missing_config_runs_with_default_sources(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            result = self._run_inventory(tmp, tmp / "missing-core-skills.yaml")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("0 skills", result.stdout)
            # 写入发生在隔离数据根，不落源码树/真实根。
            self.assertTrue((tmp / "state" / "runtime" / "skill-inventory.json").exists())

    @unittest.skipUnless(HAS_YAML, "optional YAML configuration requires PyYAML")
    def test_malformed_config_reports_actionable_error(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            bad = tmp / "bad-core-skills.yaml"
            bad.write_text("skill_sources: [unclosed", encoding="utf-8")
            result = self._run_inventory(tmp, bad, with_yaml=True)
            self.assertEqual(result.returncode, 2, result.stdout)
            self.assertIn("无法读取 skill_sources 配置", result.stderr)

    def test_missing_yaml_blocks_custom_config_without_creating_state(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            skill = tmp / "skill"
            (skill / "config").mkdir(parents=True)
            (skill / "config/data_root.yaml").write_text(f'data_root: "{tmp / "custom"}"\n')
            code = ("import sys; sys.path.insert(0, sys.argv[1]); "
                    "sys.argv = ['public_workflow.py', 'scan']; "
                    "import public_workflow; raise SystemExit(public_workflow.main())")
            env = dict(os.environ, HOME=str(home), SELF_EVOLVE_SKILL_ROOT=str(skill))
            env.pop("SELF_EVOLVE_DATA_ROOT", None)
            # -S plus an empty PYTHONPATH makes the optional dependency genuinely
            # absent, so the fail-closed path is exercised on every interpreter
            # instead of depending on whether PyYAML happens to be installed.
            env.pop("PYTHONPATH", None)
            proc = subprocess.run([sys.executable, "-S", "-c", code, str(SCRIPTS_DIR), "scan"],
                                  capture_output=True, text=True, env=env, timeout=60)
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertIn("PyYAML", proc.stdout + proc.stderr)
            self.assertFalse((tmp / "custom").exists())
            self.assertFalse(_platform_default(home).exists())


if __name__ == "__main__":
    unittest.main()
