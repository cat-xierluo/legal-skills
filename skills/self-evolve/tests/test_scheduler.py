from __future__ import annotations

import importlib.util
import json
import multiprocessing
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from unittest import mock
from pathlib import Path

HAS_YAML = importlib.util.find_spec("yaml") is not None


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCHEDULER = SKILL_ROOT / "scripts" / "scheduler_run.py"


def _run_cli_after_barrier(
    barrier: multiprocessing.synchronize.Barrier,
    results: multiprocessing.queues.Queue,
    command: list[str],
    env: dict[str, str],
) -> None:
    try:
        barrier.wait(timeout=20)
        completed = subprocess.run(command, env=env, text=True, capture_output=True, check=False)
        results.put((completed.returncode, completed.stdout, completed.stderr))
    except BaseException as exc:
        results.put((-999, "", f"{type(exc).__name__}: {exc}"))


def _persist_record_after_barrier(
    barrier: multiprocessing.synchronize.Barrier,
    results: multiprocessing.queues.Queue,
    scheduler: str,
    skill_root: str,
    data_root: str,
    index: int,
) -> None:
    try:
        for key in (
            "SELF_EVOLVE_RUNTIME_ROOT",
            "SELF_EVOLVE_STATE_ROOT",
            "SKILL_EVOLVE_STATE_ROOT",
        ):
            os.environ.pop(key, None)
        os.environ["SELF_EVOLVE_SKILL_ROOT"] = skill_root
        os.environ["SELF_EVOLVE_DATA_ROOT"] = data_root
        scheduler_path = Path(scheduler)
        sys.path.insert(0, str(scheduler_path.parent))
        module_name = f"scheduler_run_concurrency_{os.getpid()}"
        spec = importlib.util.spec_from_file_location(module_name, scheduler_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("无法加载 scheduler_run.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        barrier.wait(timeout=20)
        record = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "task_id": f"parallel-task-{index}",
            "status": "success",
            "reason": "completed",
            "duration_seconds": 0.01,
        }
        results.put((index, module.persist_record(record), ""))
    except BaseException as exc:
        results.put((index, False, f"{type(exc).__name__}: {exc}"))


def task_yaml(
    *,
    enabled: bool = True,
    command_type: str = "render_panel",
    args: str = "{}",
    task_id: str = "test-task",
    max_runs_per_day: int = 3,
) -> str:
    return textwrap.dedent(
        f"""
        schema_version: "2.0"
        tasks:
          - id: {task_id}
            name: Test task
            runner:
              enabled: {str(enabled).lower()}
              external_only: true
            recommended_schedule:
              cron: "0 1 * * *"
              timezone: Asia/Shanghai
            command:
              type: {command_type}
              args: {args}
            run_policy:
              overlap: skip
              timeout_minutes: 1
              max_runs_per_day: {max_runs_per_day}
        """
    ).lstrip()


@unittest.skipUnless(HAS_YAML, "optional YAML configuration requires PyYAML")
class ReleaseScheduleDefaultsTests(unittest.TestCase):
    def test_example_disabled_valid_and_missing_config_guidance(self):
        import yaml
        config = yaml.safe_load((SKILL_ROOT / "config/scheduled_tasks.example.yaml").read_text())
        self.assertTrue(config["tasks"])
        self.assertTrue(all(task["runner"]["enabled"] is False for task in config["tasks"]))
        valid = subprocess.run([sys.executable, str(SCHEDULER), "--config", str(SKILL_ROOT / "config/scheduled_tasks.example.yaml"), "--validate-config"], capture_output=True, text=True)
        self.assertEqual(valid.returncode, 0, valid.stderr + valid.stdout)
        with tempfile.TemporaryDirectory() as td:
            missing = subprocess.run([sys.executable, str(SCHEDULER), "--config", str(Path(td) / "missing.yaml"), "--validate-config"], capture_output=True, text=True)
        self.assertEqual(missing.returncode, 2)
        self.assertIn("scheduled_tasks.example.yaml", missing.stderr)
        self.assertIn("显式启用", missing.stderr)

    def test_missing_panel_config_and_platform_suggestions(self):
        sys.path.insert(0, str(SKILL_ROOT / "scripts"))
        import render_panel
        import setup_platform_schedule
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(render_panel, "CONFIG_PATH", Path(td) / "missing.yaml"), mock.patch.object(render_panel, "scheduler_log_paths", return_value=[]):
                scheduler = render_panel.collect_scheduler()
                self.assertEqual(scheduler["config_status"], "未配置")
                self.assertFalse(scheduler["config_error"])
            with mock.patch.object(setup_platform_schedule, "SKILL_ROOT", Path(td)):
                self.assertNotIn("openclaw cron add", setup_platform_schedule.openclaw_suggestion())
        self.assertIn("<your-timezone>", setup_platform_schedule.qwenwork_suggestion())
        self.assertIn("enabled: false", setup_platform_schedule.qwenwork_suggestion())
        self.assertIn("<your-timezone>", setup_platform_schedule.myagents_suggestion())

    def test_ignore_local_config_not_examples(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            (repo / ".gitignore").write_bytes((SKILL_ROOT / ".gitignore").read_bytes())
            for path in ("config/abc.local.yaml", "config/scheduled_tasks.yaml", "state/thing"):
                result = subprocess.run(["git", "-C", str(repo), "check-ignore", "--no-index", path], capture_output=True)
                self.assertEqual(result.returncode, 0, path)
            for path in ("config/scheduled_tasks.example.yaml", "config/release-files.json"):
                result = subprocess.run(["git", "-C", str(repo), "check-ignore", "--no-index", path], capture_output=True)
                self.assertEqual(result.returncode, 1, path)



@unittest.skipUnless(HAS_YAML, "optional YAML configuration requires PyYAML")
class SchedulerCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.fake_skill = self.root / "skill"
        (self.fake_skill / "scripts").mkdir(parents=True)
        (self.fake_skill / "SKILL.md").write_text("---\nname: self-evolve\n---\n", encoding="utf-8")
        self.data_root = self.root / "data"
        self.config = self.root / "tasks.yaml"
        self.marker = self.root / "marker.json"
        self.env = dict(os.environ)
        self.env.update(
            {
                "SELF_EVOLVE_SKILL_ROOT": str(self.fake_skill),
                "SELF_EVOLVE_DATA_ROOT": str(self.data_root),
                "SCHEDULER_TEST_MARKER": str(self.marker),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def install_fake_render(self) -> None:
        script = self.fake_skill / "scripts" / "render_panel.py"
        script.write_text(
            textwrap.dedent(
                """
                import json
                import os
                import sys
                from pathlib import Path
                Path(os.environ["SCHEDULER_TEST_MARKER"]).write_text(
                    json.dumps(sys.argv[1:]), encoding="utf-8"
                )
                """
            ).lstrip(),
            encoding="utf-8",
        )

    def install_counting_render(self) -> None:
        script = self.fake_skill / "scripts" / "render_panel.py"
        script.write_text(
            textwrap.dedent(
                """
                import json
                import os
                import sys
                import time
                marker = os.environ["SCHEDULER_TEST_MARKER"]
                fd = os.open(marker, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
                try:
                    os.write(fd, (json.dumps(sys.argv[1:]) + "\\n").encode("utf-8"))
                    os.fsync(fd)
                finally:
                    os.close(fd)
                time.sleep(0.35)
                """
            ).lstrip(),
            encoding="utf-8",
        )

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCHEDULER), "--config", str(self.config), *args],
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )

    def parse_result(self, completed: subprocess.CompletedProcess[str]) -> dict:
        self.assertTrue(completed.stdout.strip(), completed.stderr)
        return json.loads(completed.stdout)

    def claim_data_root(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                "from self_evolve_paths import assert_runtime_ready; assert_runtime_ready()",
            ],
            cwd=str(SCHEDULER.parent),
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def run_cli_concurrently(self, count: int, *args: str) -> list[subprocess.CompletedProcess[str]]:
        context = multiprocessing.get_context("spawn")
        barrier = context.Barrier(count + 1)
        results = context.Queue()
        command = [sys.executable, str(SCHEDULER), "--config", str(self.config), *args]
        processes = [
            context.Process(
                target=_run_cli_after_barrier,
                args=(barrier, results, command, self.env),
            )
            for _ in range(count)
        ]
        try:
            for process in processes:
                process.start()
            barrier.wait(timeout=20)
            # Drain before joining: a worker cannot exit while its Queue feeder
            # is blocked writing a CLI result larger than the pipe buffer.
            completed = []
            for _ in processes:
                returncode, stdout, stderr = results.get(timeout=30)
                completed.append(
                    subprocess.CompletedProcess(command, returncode, stdout=stdout, stderr=stderr)
                )
            for process in processes:
                process.join(timeout=5)
                self.assertFalse(process.is_alive(), "并发 scheduler 子进程未按时退出")
                self.assertEqual(process.exitcode, 0)
            return completed
        finally:
            # Reap only this test's children even when an assertion/timeout fails.
            for process in processes:
                if process.pid is not None:
                    if process.is_alive():
                        process.terminate()
                    process.join(timeout=5)
                    if process.is_alive():
                        process.kill()
                        process.join(timeout=5)
            results.close()
            results.join_thread()

    def test_schema_v2_validates_even_when_optional_deep_dream_script_is_absent(self) -> None:
        self.config.write_text(task_yaml(command_type="deep_dream"), encoding="utf-8")
        completed = self.run_cli("--validate-config", "--json")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(self.parse_result(completed)["task_count"], 1)

        run = self.run_cli(
            "--task", "test-task", "--run-now", "--trigger", "external", "--json"
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        result = self.parse_result(run)
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "not_implemented")

    def test_config_rejects_unknown_command_argument(self) -> None:
        self.config.write_text(task_yaml(args="{shell: 'rm -rf /'}"), encoding="utf-8")
        completed = self.run_cli("--validate-config", "--json")
        self.assertEqual(completed.returncode, 2)
        result = self.parse_result(completed)
        self.assertFalse(result["valid"])
        self.assertTrue(any("不在 render_panel 白名单" in item for item in result["errors"]))

    def test_external_only_requires_explicit_external_trigger(self) -> None:
        self.install_fake_render()
        self.config.write_text(task_yaml(), encoding="utf-8")
        completed = self.run_cli("--task", "test-task", "--run-now", "--json")
        self.assertEqual(completed.returncode, 1, completed.stderr)
        result = self.parse_result(completed)
        self.assertEqual(result["reason"], "external_trigger_required")
        self.assertIn("--trigger external", result["next_action"])
        self.assertFalse(self.marker.exists())

    def test_allow_disabled_is_ignored_and_never_bypasses_kill_switch(self) -> None:
        self.install_fake_render()
        self.config.write_text(task_yaml(enabled=False), encoding="utf-8")
        completed = self.run_cli(
            "--task",
            "test-task",
            "--run-now",
            "--trigger",
            "external",
            "--allow-disabled",
            "--json",
        )
        self.assertEqual(completed.returncode, 1, completed.stderr)
        self.assertIn("已废弃且被忽略", completed.stderr)
        self.assertEqual(self.parse_result(completed)["reason"], "runner_disabled")
        self.assertFalse(self.marker.exists())

    def test_legacy_in_tree_state_blocks_execution_until_migrated(self) -> None:
        self.install_fake_render()
        self.config.write_text(task_yaml(), encoding="utf-8")
        legacy = self.fake_skill / "runtime" / "old.json"
        legacy.parent.mkdir(parents=True)
        legacy.write_text("{}\n", encoding="utf-8")
        completed = self.run_cli(
            "--task", "test-task", "--run-now", "--trigger", "external", "--json"
        )
        self.assertEqual(completed.returncode, 1, completed.stderr)
        result = self.parse_result(completed)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "migration_required")
        self.assertIn("migrate_state.py --apply", result["next_action"])
        self.assertFalse(self.marker.exists())

    def test_external_run_recovers_dead_pid_lock_and_uses_monthly_log(self) -> None:
        self.install_fake_render()
        self.config.write_text(task_yaml(args="{limit: 25}"), encoding="utf-8")
        self.claim_data_root()
        lock = self.data_root / "runtime" / "scheduler" / "locks" / "test-task.lock"
        lock.parent.mkdir(parents=True)
        lock.write_text(
            json.dumps({"pid": 2_147_483_647, "created_at": time.time(), "token": "old"}),
            encoding="utf-8",
        )
        completed = self.run_cli(
            "--task", "test-task", "--run-now", "--trigger", "external", "--json"
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = self.parse_result(completed)
        self.assertEqual(result["status"], "success")
        self.assertTrue(result["lock_recovered"])
        self.assertFalse(lock.exists())
        self.assertEqual(json.loads(self.marker.read_text(encoding="utf-8")), ["--json", "--limit", "25"])
        logs = list((self.data_root / "runtime" / "scheduler" / "task-runs").glob("????-??.jsonl"))
        self.assertEqual(len(logs), 1)

    def test_completed_backfill_is_persisted_only_once(self) -> None:
        self.config.write_text(
            task_yaml(command_type="dream_sweep", task_id="history-backfill-index"),
            encoding="utf-8",
        )
        self.claim_data_root()
        backfill = self.data_root / "runtime" / "dreaming" / "backfill-state.json"
        backfill.parent.mkdir(parents=True)
        backfill.write_text('{"completed": true}\n', encoding="utf-8")
        command = (
            "--task",
            "history-backfill-index",
            "--run-now",
            "--trigger",
            "external",
            "--json",
        )
        first = self.run_cli(*command)
        second = self.run_cli(*command)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertTrue(self.parse_result(first)["persisted"])
        self.assertFalse(self.parse_result(second)["persisted"])
        run_log = next((self.data_root / "runtime" / "scheduler" / "task-runs").glob("*.jsonl"))
        self.assertEqual(len(run_log.read_text(encoding="utf-8").splitlines()), 1)

    def test_same_task_concurrency_reserves_only_one_daily_run(self) -> None:
        self.install_counting_render()
        self.config.write_text(task_yaml(max_runs_per_day=1), encoding="utf-8")
        completed = self.run_cli_concurrently(
            2,
            "--task",
            "test-task",
            "--run-now",
            "--trigger",
            "external",
            "--json",
        )

        records = [self.parse_result(item) for item in completed]
        self.assertEqual(sum(item["status"] == "success" for item in records), 1)
        self.assertEqual(sum(item["status"] in {"skipped", "blocked"} for item in records), 1)
        self.assertIn(
            next(item["reason"] for item in records if item["status"] != "success"),
            {"already_running", "max_runs_per_day_reached"},
        )
        for completed_item, record in zip(completed, records):
            self.assertEqual(completed_item.returncode, 1 if record["status"] == "blocked" else 0)
        marker_lines = self.marker.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(marker_lines), 1, marker_lines)

        run_log = next((self.data_root / "runtime" / "scheduler" / "task-runs").glob("*.jsonl"))
        persisted = [json.loads(line) for line in run_log.read_text(encoding="utf-8").splitlines()]
        attempts = [
            item
            for item in persisted
            if item["task_id"] == "test-task" and item.get("record_type") == "attempt"
        ]
        results = [
            item
            for item in persisted
            if item["task_id"] == "test-task" and item.get("record_type") == "result"
        ]
        self.assertEqual(len(attempts), 1)
        self.assertEqual(len(results), 1)
        self.assertEqual(attempts[0]["run_id"], results[0]["run_id"])

    def test_daily_quota_is_blocking_nonzero_with_next_action(self) -> None:
        self.install_fake_render()
        self.config.write_text(task_yaml(max_runs_per_day=1), encoding="utf-8")
        command = (
            "--task",
            "test-task",
            "--run-now",
            "--trigger",
            "external",
            "--json",
        )
        first = self.run_cli(*command)
        second = self.run_cli(*command)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 1, second.stderr)
        result = self.parse_result(second)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "max_runs_per_day_reached")
        self.assertTrue(result["next_action"])

    def test_attempt_and_result_share_run_id_without_double_charging_quota(self) -> None:
        self.install_fake_render()
        self.config.write_text(task_yaml(max_runs_per_day=2), encoding="utf-8")
        command = (
            "--task",
            "test-task",
            "--run-now",
            "--trigger",
            "external",
            "--json",
        )
        first = self.run_cli(*command)
        second = self.run_cli(*command)
        third = self.run_cli(*command)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(third.returncode, 1, third.stderr)
        self.assertEqual(self.parse_result(third)["reason"], "max_runs_per_day_reached")

        run_log = next(
            (self.data_root / "runtime" / "scheduler" / "task-runs").glob("*.jsonl")
        )
        records = [json.loads(line) for line in run_log.read_text(encoding="utf-8").splitlines()]
        attempts = [item for item in records if item.get("record_type") == "attempt"]
        results = [item for item in records if item.get("record_type") == "result"]
        self.assertEqual(len(attempts), 2)
        self.assertEqual(len(results), 2)
        self.assertEqual({item["run_id"] for item in attempts}, {item["run_id"] for item in results})
        self.assertEqual(len({item["run_id"] for item in attempts}), 2)
        self.assertTrue(
            all(item.get("process_start_token") or item.get("boot_id") for item in attempts)
        )
        self.assertTrue(
            all(item["expires_at_epoch"] > item["reserved_at_epoch"] for item in attempts)
        )

    def test_crash_after_reservation_still_consumes_daily_quota(self) -> None:
        self.install_fake_render()
        self.config.write_text(task_yaml(max_runs_per_day=1), encoding="utf-8")
        crash_code = textwrap.dedent(
            f"""
            import importlib.util
            import json
            import os
            import sys
            from pathlib import Path

            scheduler_path = Path({str(SCHEDULER)!r})
            sys.path.insert(0, str(scheduler_path.parent))
            spec = importlib.util.spec_from_file_location("scheduler_crash_reserve", scheduler_path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            module.assert_runtime_ready()
            lock = module.TaskLock("test-task", stale_after_seconds=360)
            if not lock.acquire():
                raise SystemExit("could not acquire task lock")
            reservation, error = module.reserve_daily_run("test-task", 1, lock)
            print(json.dumps({{"reservation": reservation, "error": error}}), flush=True)
            os._exit(0)
            """
        )
        crashed = subprocess.run(
            [sys.executable, "-c", crash_code],
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(crashed.returncode, 0, crashed.stderr)
        crash_result = json.loads(crashed.stdout)
        self.assertIsNotNone(crash_result["reservation"])
        self.assertEqual(crash_result["error"], "")

        blocked = self.run_cli(
            "--task", "test-task", "--run-now", "--trigger", "external", "--json"
        )
        self.assertEqual(blocked.returncode, 1, blocked.stderr)
        result = self.parse_result(blocked)
        self.assertEqual(result["reason"], "max_runs_per_day_reached")
        self.assertTrue(result["lock_recovered"])
        self.assertFalse(self.marker.exists())
        run_log = next(
            (self.data_root / "runtime" / "scheduler" / "task-runs").glob("*.jsonl")
        )
        records = [json.loads(line) for line in run_log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(sum(item.get("record_type") == "attempt" for item in records), 1)
        self.assertEqual(sum(item.get("record_type") == "result" for item in records), 0)

    def test_expired_active_run_with_live_pid_is_recoverable(self) -> None:
        self.install_fake_render()
        self.config.write_text(task_yaml(), encoding="utf-8")
        self.claim_data_root()
        now = time.time()
        state_path = self.data_root / "runtime" / "scheduler" / "task-state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(
                {
                    "test-task": {
                        "active_run": {
                            "run_id": "a" * 32,
                            "owner_token": "expired-owner",
                            "pid": os.getpid(),
                            "process_start_token": "b" * 64,
                            "reserved_at_epoch": now - 1_000,
                            "expires_at_epoch": now - 1,
                        }
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )
        completed = self.run_cli(
            "--task", "test-task", "--run-now", "--trigger", "external", "--json"
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(self.parse_result(completed)["status"], "success")
        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertNotIn("active_run", state["test-task"])

    def test_reused_live_pid_with_wrong_start_token_is_recoverable(self) -> None:
        self.install_fake_render()
        self.config.write_text(task_yaml(), encoding="utf-8")
        self.claim_data_root()
        now = time.time()
        state_path = self.data_root / "runtime" / "scheduler" / "task-state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(
                {
                    "test-task": {
                        "active_run": {
                            "run_id": "c" * 32,
                            "owner_token": "reused-pid-owner",
                            "pid": os.getpid(),
                            "process_start_token": "d" * 64,
                            "reserved_at_epoch": now,
                            "expires_at_epoch": now + 300,
                        }
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )
        completed = self.run_cli(
            "--task", "test-task", "--run-now", "--trigger", "external", "--json"
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(self.parse_result(completed)["status"], "success")

    def test_corrupt_current_month_log_blocks_without_appending(self) -> None:
        self.install_fake_render()
        self.config.write_text(task_yaml(), encoding="utf-8")
        self.claim_data_root()
        run_log = (
            self.data_root
            / "runtime"
            / "scheduler"
            / "task-runs"
            / f"{time.strftime('%Y-%m')}.jsonl"
        )
        run_log.parent.mkdir(parents=True, exist_ok=True)
        corrupt_payload = b'{"record_type":"attempt"\n'
        run_log.write_bytes(corrupt_payload)

        completed = self.run_cli(
            "--task", "test-task", "--run-now", "--trigger", "external", "--json"
        )
        self.assertEqual(completed.returncode, 1, completed.stderr)
        result = self.parse_result(completed)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "scheduler_run_log_corrupt")
        self.assertTrue(result["next_action"])
        self.assertFalse(result["persisted"])
        self.assertFalse(self.marker.exists())
        self.assertEqual(run_log.read_bytes(), corrupt_payload)

    def test_parallel_task_state_merges_and_jsonl_records_remain_valid(self) -> None:
        worker_count = 12
        context = multiprocessing.get_context("spawn")
        barrier = context.Barrier(worker_count + 1)
        results = context.Queue()
        processes = [
            context.Process(
                target=_persist_record_after_barrier,
                args=(
                    barrier,
                    results,
                    str(SCHEDULER),
                    str(self.fake_skill),
                    str(self.data_root),
                    index,
                ),
            )
            for index in range(worker_count)
        ]
        for process in processes:
            process.start()
        barrier.wait(timeout=20)
        for process in processes:
            process.join(timeout=30)
            self.assertFalse(process.is_alive(), "并发持久化子进程未按时退出")
            self.assertEqual(process.exitcode, 0)
        worker_results = [results.get(timeout=5) for _ in processes]
        results.close()
        results.join_thread()
        self.assertTrue(all(persisted and not error for _, persisted, error in worker_results), worker_results)

        scheduler_root = self.data_root / "runtime" / "scheduler"
        state = json.loads((scheduler_root / "task-state.json").read_text(encoding="utf-8"))
        expected_ids = {f"parallel-task-{index}" for index in range(worker_count)}
        self.assertEqual(set(state), expected_ids)
        run_log = next((scheduler_root / "task-runs").glob("*.jsonl"))
        lines = run_log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), worker_count)
        records = [json.loads(line) for line in lines]
        self.assertEqual({item["task_id"] for item in records}, expected_ids)
        self.assertTrue((scheduler_root / "locks" / ".scheduler-transaction.lock").is_file())


class BackfillRecheckTests(unittest.TestCase):
    """backfill_is_complete 在新源文件出现后应重新打开，避免永久 completed 锁死。"""

    def setUp(self) -> None:
        scripts_dir = str(SCHEDULER.parent)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        spec = importlib.util.spec_from_file_location("scheduler_backfill_recheck", SCHEDULER)
        assert spec is not None and spec.loader is not None
        self.module = importlib.util.module_from_spec(spec)
        sys.modules["scheduler_backfill_recheck"] = self.module
        spec.loader.exec_module(self.module)

    @staticmethod
    def _payload(completed: bool, total_discovered=None) -> dict:
        payload: dict = {"completed": completed}
        if total_discovered is not None:
            payload["last_run"] = {"total_discovered": total_discovered}
        return payload

    def test_completed_false_is_not_complete(self) -> None:
        with mock.patch.object(self.module, "load_json", return_value={"completed": False}):
            self.assertFalse(self.module.backfill_is_complete())

    def test_completed_without_last_run_skips_recheck(self) -> None:
        """无 last_run（legacy/测试态）不复核，维持 completed——保护现有 skip 语义。"""
        with mock.patch.object(self.module, "load_json", return_value={"completed": True}):
            with mock.patch.object(self.module, "_count_raw_source_files", return_value=999) as counter:
                self.assertTrue(self.module.backfill_is_complete())
                counter.assert_not_called()

    def test_completed_with_new_files_reopens(self) -> None:
        """completed 后源文件增多 → 解锁，允许 backfill 重跑补采。"""
        with mock.patch.object(self.module, "load_json", return_value=self._payload(True, 100)):
            with mock.patch.object(self.module, "_count_raw_source_files", return_value=150):
                self.assertFalse(self.module.backfill_is_complete())

    def test_completed_with_no_new_files_stays_complete(self) -> None:
        with mock.patch.object(self.module, "load_json", return_value=self._payload(True, 100)):
            with mock.patch.object(self.module, "_count_raw_source_files", return_value=100):
                self.assertTrue(self.module.backfill_is_complete())


if __name__ == "__main__":
    unittest.main()
