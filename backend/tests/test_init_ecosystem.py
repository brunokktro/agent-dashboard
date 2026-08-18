"""Contract tests for the runner templates scaffolded by bin/init-ecosystem.

Real artifacts, no mocks: the script is actually executed against a temp
ecosystem, and the scaffolded runner is invoked exactly the way the dashboard
invokes it (see api.py trigger_agent), with a fake kiro-cli capturing argv.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
INIT_ECOSYSTEM = REPO_ROOT / "bin" / "init-ecosystem"


@pytest.fixture()
def scaffolded(tmp_path: Path) -> Path:
    """Run bin/init-ecosystem --runners against a temp agents dir."""
    agents = tmp_path / "agents"
    agents.mkdir()
    r = subprocess.run(
        [str(INIT_ECOSYSTEM), "--runners"],
        env={**os.environ, "DASHBOARD_AGENTS_DIR": str(agents)},
        capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    runner = agents / "scripts" / "run-agent.sh"
    assert runner.is_file(), "init-ecosystem did not scaffold run-agent.sh"
    return agents


def _fake_kiro_cli(bin_dir: Path, capture: Path) -> None:
    """A kiro-cli that records its argv, one arg per line."""
    fake = bin_dir / "kiro-cli"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        f'printf "%s\\n" "$@" > "{capture}"\n')
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)


def test_scaffolded_runner_does_not_duplicate_no_interactive(scaffolded, tmp_path):
    """Regression (field report): the dashboard's Run button calls
    ``run-agent.sh <name> run --no-interactive`` (api.py trigger_agent, and
    the documented contract in README 'Runner scripts'). The scaffolded
    template ALSO hardcodes ``--no-interactive`` on its RUN line and forwards
    ``"$@"``, so kiro-cli received the flag twice and aborted with
    ``error: the argument '--no-interactive' cannot be used multiple times``.
    The template must pass the flag exactly once."""
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    capture = tmp_path / "argv.txt"
    _fake_kiro_cli(bin_dir, capture)

    runner = scaffolded / "scripts" / "run-agent.sh"
    r = subprocess.run(
        # exact invocation shape used by api.py trigger_agent
        [str(runner), "alpha-agent", "run", "--no-interactive"],
        env={**os.environ,
             "PATH": f"{bin_dir}:{os.environ['PATH']}",
             "DASHBOARD_AGENTS_DIR": str(scaffolded),
             # point at an empty dir so record-run is absent and the runner
             # execs the RUN command directly (the unrecorded path)
             "DASHBOARD_DIR": str(tmp_path / "no-dashboard"),
             "AGENT_CLI_NAME": "alpha-cli-name"},
        capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    assert capture.exists(), "kiro-cli was never invoked"

    argv = capture.read_text().splitlines()
    assert argv.count("--no-interactive") == 1, argv
    # the rest of the contract still holds
    assert argv[:3] == ["chat", "--agent", "alpha-cli-name"], argv
    assert "run" in argv, argv


def test_scaffolded_runner_is_non_interactive_even_without_caller_flags(scaffolded, tmp_path):
    """Manual invocation (``run-agent.sh <name>``) must stay non-interactive:
    the runner wraps unattended ad-hoc runs, never a live session."""
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    capture = tmp_path / "argv.txt"
    _fake_kiro_cli(bin_dir, capture)

    runner = scaffolded / "scripts" / "run-agent.sh"
    r = subprocess.run(
        [str(runner), "alpha-agent"],
        env={**os.environ,
             "PATH": f"{bin_dir}:{os.environ['PATH']}",
             "DASHBOARD_AGENTS_DIR": str(scaffolded),
             "DASHBOARD_DIR": str(tmp_path / "no-dashboard")},
        capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    argv = capture.read_text().splitlines()
    assert argv.count("--no-interactive") == 1, argv
