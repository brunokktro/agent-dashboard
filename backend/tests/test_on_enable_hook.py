"""setup.onEnable contract (issue #5).

The expectation comes from app.json itself: the hook string that KiroCrew runs and the `ui.entry`
it must produce. A fake `npm` stands in for the real build (it writes the entry the real build would
write), so the test proves WHICH trees get built, in which state, and that the declared entry exists
afterwards. The real-npm run is recorded on the issue.
"""

from __future__ import annotations

import json
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
APP = json.loads((REPO / "app.json").read_text())
HOOK = APP["setup"]["onEnable"]

pytestmark = pytest.mark.skipif(sys.platform == "win32",
                                reason="KiroCrew does not run onEnable on native Windows")

FAKE_NPM = """#!/bin/sh
echo "$(basename "$PWD") $*" >> "$NPM_LOG"
if [ "$1" = "run" ] && [ "$2" = "build" ]; then
  case "$(basename "$PWD")" in
    frontend) mkdir -p dist && echo ok > dist/index.html ;;
    ui) mkdir -p "$(dirname "$UI_ENTRY")" && echo ok > "$UI_ENTRY" ;;
  esac
fi
"""


def _app(tmp_path: Path, *, frontend: bool, ui: bool, node_modules: bool) -> Path:
    root = tmp_path / "app"
    (root / "bin").mkdir(parents=True)
    shutil.copy(REPO / "app.json", root / "app.json")
    shutil.copy(REPO / "bin" / "ensure-bundles.mjs", root / "bin" / "ensure-bundles.mjs")
    for tree, present, entry in (("frontend", frontend, "dist/index.html"),
                                 ("ui", ui, APP["ui"]["entry"])):
        (root / tree).mkdir()
        if node_modules:
            (root / tree / "node_modules").mkdir()
        if present:
            target = root / tree / entry
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("prebuilt")
    return root


def _enable(root: Path, tmp_path: Path, no_node: bool = False, expect_ok: bool = True) -> list[str]:
    bindir = tmp_path / "fakebin"
    bindir.mkdir(exist_ok=True)
    npm = bindir / "npm"
    npm.write_text(FAKE_NPM)
    npm.chmod(npm.stat().st_mode | stat.S_IXUSR)
    log = tmp_path / "npm.log"
    log.write_text("")
    node = shutil.which("node")
    assert node, "node is required to run the hook"
    path = f"{bindir}:/usr/bin:/bin" if no_node else f"{bindir}:{Path(node).parent}:/usr/bin:/bin"
    env = {"PATH": path, "NPM_LOG": str(log),
           "UI_ENTRY": str(root / "ui" / APP["ui"]["entry"])}
    # KiroCrew runs the hook through /bin/bash from the app root.
    out = subprocess.run(["/bin/bash", "-c", HOOK], cwd=root, env=env, capture_output=True,
                         text=True, timeout=60)
    assert (out.returncode == 0) == expect_ok, out.stdout + out.stderr
    return [line for line in log.read_text().splitlines() if line]


def test_release_install_with_both_bundles_does_no_npm_work(tmp_path) -> None:
    root = _app(tmp_path, frontend=True, ui=True, node_modules=False)
    assert _enable(root, tmp_path) == []


def test_missing_ui_bundle_builds_only_ui(tmp_path) -> None:
    root = _app(tmp_path, frontend=True, ui=False, node_modules=False)
    calls = _enable(root, tmp_path)
    assert calls == ["ui ci --no-audit --no-fund", "ui run build"]
    assert (root / "ui" / APP["ui"]["entry"]).is_file()


def test_missing_frontend_bundle_builds_only_frontend(tmp_path) -> None:
    root = _app(tmp_path, frontend=False, ui=True, node_modules=False)
    assert _enable(root, tmp_path) == ["frontend ci --no-audit --no-fund", "frontend run build"]
    assert (root / "frontend" / "dist" / "index.html").is_file()


def test_source_install_builds_both_and_declared_entry_exists(tmp_path) -> None:
    root = _app(tmp_path, frontend=False, ui=False, node_modules=False)
    calls = _enable(root, tmp_path)
    assert [c.split()[0] for c in calls if c.endswith("run build")] == ["frontend", "ui"]
    assert (root / "ui" / APP["ui"]["entry"]).is_file(), "ui.entry from app.json still absent"


def test_existing_node_modules_skips_install(tmp_path) -> None:
    root = _app(tmp_path, frontend=False, ui=False, node_modules=True)
    assert _enable(root, tmp_path) == ["frontend run build", "ui run build"]


def test_release_install_without_node_succeeds_and_runs_nothing(tmp_path) -> None:
    """No Node on the target machine (catalog promise): a release install still enables."""
    root = _app(tmp_path, frontend=True, ui=True, node_modules=False)
    assert _enable(root, tmp_path, no_node=True) == []


def test_without_node_a_missing_bundle_fails_instead_of_passing(tmp_path) -> None:
    root = _app(tmp_path, frontend=True, ui=False, node_modules=False)
    assert _enable(root, tmp_path, no_node=True, expect_ok=False) == []


def test_shell_fallback_checks_the_declared_ui_entry() -> None:
    assert f"ui/{APP['ui']['entry']}" in HOOK and "frontend/dist/index.html" in HOOK
