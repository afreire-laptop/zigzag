"""Each hardening check fails the smoke test when its property does not hold. A stub `docker` stands in."""

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.support import SCRIPTS

GOOD = {"api_uid": "10001", "web_uid": "101", "api_ports": "8000/tcp", "buffering": "yes", "bind": "127.0.0.1"}
STUB = """#!/bin/sh
case "$*" in
  *"exec -T api id -u"*) echo "{api_uid}" ;;
  *"exec -T web id -u"*) echo "{web_uid}" ;;
  *"ps api --format"*) echo "{api_ports}" ;;
  *"nginx -T"*)
    printf 'location ~ ^/api/operations/[^/]+/events$ {{\\n'
    [ "{buffering}" = yes ] && printf '  proxy_buffering off;\\n'
    printf '}}\\n' ;;
  *"ps --format"*) echo "web {bind}:18080->8080/tcp" ;;
esac
"""


class SmokeHardeningTest(unittest.TestCase):
    def run_checks(self, **overrides: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            docker = Path(tmp) / "docker"
            docker.write_text(STUB.format(**{**GOOD, **overrides}))
            docker.chmod(docker.stat().st_mode | stat.S_IEXEC)
            return subprocess.run(
                ["sh", str(SCRIPTS / "smoke_hardening.sh"), "proj", "18080"],
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "PATH": f"{tmp}:{os.environ['PATH']}"},
            )

    def test_all_properties_hold(self) -> None:
        run = self.run_checks()
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout.count("ok "), 5)

    def test_each_violated_property_fails_the_run(self) -> None:
        cases = {
            "the API runs as a non-root user": {"api_uid": "0"},
            "nginx runs as a non-root user": {"web_uid": "0"},
            "the API is not published to the host": {"api_ports": "0.0.0.0:8000->8000/tcp"},
            "nginx does not buffer the event stream": {"buffering": "no"},
            "the web entry point is bound to 127.0.0.1": {"bind": "0.0.0.0"},
        }
        for check, override in cases.items():
            with self.subTest(check):
                run = self.run_checks(**override)
                self.assertEqual(run.returncode, 1)
                self.assertIn(f"FAIL {check}", run.stderr)


if __name__ == "__main__":
    unittest.main()
