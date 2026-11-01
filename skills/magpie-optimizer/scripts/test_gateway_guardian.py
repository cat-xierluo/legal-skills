"""Regression: high RSS/orphan clues and legacy DRY_RUN=0 remain read-only."""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest


SCRIPT = Path(__file__).with_name("gateway_guardian.sh")


class GuardianTests(unittest.TestCase):
    def test_old_action_names_never_mutate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bindir = root / "bin"
            bindir.mkdir()
            ps = bindir / "ps"
            ps.write_text("""#!/bin/sh
if [ "${FAIL_SCAN:-}" = ps ]; then printf '31338 1 Z partial\\n'; exit 7; fi
case "$*" in
 *rss*) printf '31337 1 10485760 /example/magpie-bun\\n' ;;
 *) printf '31337 1 S /example/magpie-bun\\n31338 1 Z example\\n' ;;
esac
""")
            for cmd in ["sysctl", "uptime"]:
                (bindir / cmd).write_text('#!/bin/sh\nif [ "${FAIL_SCAN:-}" = "${0##*/}" ]; then exit 7; fi\nprintf "fixture\\n"\n')
            (bindir / "find").write_text('#!/bin/sh\nif [ "${FAIL_SCAN:-}" = find ]; then exit 7; fi\nexec /usr/bin/find "$@"\n')
            for cmd in ["kill", "launchctl", "rm", "mv"]:
                (bindir / cmd).write_text('#!/bin/sh\nprintf "%s\\n" "$0" >> "$MUTATION_SENTINEL"\nexit 99\n')
            for p in bindir.iterdir():
                p.chmod(0o700)
            env = os.environ.copy()
            env.pop("BASH_ENV", None)
            env.update(HOME=str(root), PATH=str(bindir) + ":/usr/bin:/bin:/usr/sbin:/sbin",
                       MUTATION_SENTINEL=str(root / "mutated"))
            # Cover the kill shell builtin as well as external commands.
            startup = root / "bash-env"
            startup.write_text('kill() { printf "kill\\n" >> "$MUTATION_SENTINEL"; return 99; }\n')
            env["BASH_ENV"] = str(startup)
            cache = root / ".cache/magpie/calls-v15"
            cache.mkdir(parents=True)
            for name in ["old", "two\nlines"]:
                p = cache / name
                p.write_text("private fixture")
                old = time.time() - 10 * 86400
                os.utime(p, (old, old))
            logfile = root / "Library/Logs/magpie/app.log"
            logfile.parent.mkdir(parents=True)
            logfile.write_bytes(b"x" * 2200000)

            def snapshot():
                return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in root.rglob("*") if p.is_file()}

            before = snapshot()
            for dry in ["0", "1"]:
                for mode in [None, "status", "guard", "reap", "cache", "all"]:
                    args = ["/bin/bash", str(SCRIPT)] + ([] if mode is None else [mode])
                    run = subprocess.run(args, env={**env, "DRY_RUN": dry}, capture_output=True,
                                         text=True, timeout=8)
                    self.assertEqual(run.returncode, 0, run.stderr)
                    if mode == "guard":
                        self.assertIn("GUARD_REVIEW_REQUIRED", run.stdout)
                    if mode == "reap":
                        self.assertIn("ORPHAN_REVIEW_REQUIRED", run.stdout)
                    if mode in ["cache", "all"]:
                        self.assertIn("older_than_7_days=2", run.stdout)
                    self.assertEqual(snapshot(), before, (dry, mode))
            bad = subprocess.run(["/bin/bash", str(SCRIPT), "unknown"], env=env,
                                 capture_output=True, timeout=8)
            self.assertEqual(bad.returncode, 2)
            for mode, fail in [("status", "sysctl"), ("all", "uptime"),
                               ("guard", "ps"), ("reap", "ps"),
                               ("cache", "find"), ("all", "find")]:
                run = subprocess.run(["/bin/bash", str(SCRIPT), mode],
                                     env={**env, "FAIL_SCAN": fail}, capture_output=True,
                                     text=True, timeout=8)
                self.assertNotEqual(run.returncode, 0, (mode, fail))
                if fail == "ps":
                    self.assertNotIn("ZOMBIES count=", run.stdout)
                    self.assertNotIn("HOST_CANDIDATE", run.stdout)
                if fail == "find":
                    self.assertNotIn("CACHE_REPORT", run.stdout)
                self.assertEqual(snapshot(), before, (mode, fail))

    def test_invalid_threshold_fails(self):
        env = {**os.environ, "MAGPIE_RSS_LIMIT_MB": "2; kill 1"}
        env.pop("BASH_ENV", None)
        for mode in ["guard", "status", "all"]:
            run = subprocess.run(["/bin/bash", str(SCRIPT), mode], env=env,
                                 capture_output=True, timeout=8)
            self.assertNotEqual(run.returncode, 0)


if __name__ == "__main__":
    unittest.main()
