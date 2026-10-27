from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
LEGACY_HOOK = SKILL_ROOT / "scripts" / "legacy_hook.py"
if str(LEGACY_HOOK.parent) not in sys.path:
    sys.path.insert(0, str(LEGACY_HOOK.parent))

import legacy_hook as legacy  # noqa: E402


class LegacyHookCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.settings = self.root / "settings.json"
        self.original = {
            "theme": "dark",
            "hooks": {
                "SessionEnd": [
                    {
                        "matcher": "",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "python3 '/tmp/private-skills/self-evolve/scripts/sediment_guard.py'",
                            },
                            {"type": "command", "command": "python3 /tmp/keep.py"},
                        ],
                    },
                    {
                        "type": "command",
                        "command": "python3 ~/.claude/skill-evolve/scripts/sediment_guard.py",
                    },
                    {
                        "type": "command",
                        "command": "python3 /tmp/another/sediment_guard.py",
                    },
                ],
                "PreToolUse": [{"hooks": [{"type": "command", "command": "python3 /tmp/pre.py"}]}],
            },
        }
        self.settings.write_text(
            json.dumps(self.original, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_cli(self, action: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(LEGACY_HOOK), action, "--settings", str(self.settings), "--json", *args],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_status_reports_only_self_evolve_sediment_hooks(self) -> None:
        completed = self.run_cli("status")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["legacy_hook_count"], 2)
        self.assertTrue(all(len(item["command_sha256"]) == 16 for item in result["matches"]))

    def test_remove_defaults_to_dry_run(self) -> None:
        before = self.settings.read_bytes()
        completed = self.run_cli("remove")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["would_remove"], 2)
        self.assertFalse(result["applied"])
        self.assertEqual(self.settings.read_bytes(), before)
        self.assertEqual(list(self.root.glob("settings.json.bak-*")), [])

    def test_apply_removes_only_matches_and_creates_exact_backup(self) -> None:
        before = self.settings.read_bytes()
        completed = self.run_cli("remove", "--apply")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertTrue(result["applied"])
        self.assertEqual(result["removed"], 2)
        backup = Path(result["backup"])
        self.assertTrue(backup.exists())
        self.assertEqual(backup.read_bytes(), before)

        updated = json.loads(self.settings.read_text(encoding="utf-8"))
        self.assertEqual(updated["theme"], "dark")
        session_end = updated["hooks"]["SessionEnd"]
        commands = []
        for group in session_end:
            if isinstance(group, dict) and isinstance(group.get("command"), str):
                commands.append(group["command"])
            for hook in group.get("hooks", []) if isinstance(group, dict) else []:
                commands.append(hook.get("command", ""))
        self.assertIn("python3 /tmp/keep.py", commands)
        self.assertIn("python3 /tmp/another/sediment_guard.py", commands)
        self.assertNotIn("self-evolve/scripts/sediment_guard.py", "\n".join(commands))
        self.assertEqual(
            updated["hooks"]["PreToolUse"],
            self.original["hooks"]["PreToolUse"],
        )

    def test_invalid_json_is_never_overwritten(self) -> None:
        self.settings.write_text("{broken", encoding="utf-8")
        completed = self.run_cli("remove", "--apply")
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(self.settings.read_text(encoding="utf-8"), "{broken")

    def test_compare_and_swap_rejects_concurrent_settings_change(self) -> None:
        expected = legacy.settings_digest(self.settings)
        updated, _ = legacy.remove_session_end_hooks(self.original)
        concurrent = {**self.original, "theme": "light"}
        self.settings.write_text(json.dumps(concurrent), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "其他进程修改"):
            legacy.atomic_write_with_backup(
                self.settings,
                updated,
                expected_sha256=expected,
            )

        self.assertEqual(json.loads(self.settings.read_text(encoding="utf-8"))["theme"], "light")
        self.assertEqual(list(self.root.glob("settings.json.bak-*")), [])

    def test_snapshot_digest_is_derived_from_the_exact_parsed_bytes(self) -> None:
        raw = self.settings.read_bytes()
        settings, digest = legacy.load_settings_snapshot(self.settings)
        self.assertEqual(settings, self.original)
        self.assertEqual(digest, legacy.hashlib.sha256(raw).hexdigest())


if __name__ == "__main__":
    unittest.main()
