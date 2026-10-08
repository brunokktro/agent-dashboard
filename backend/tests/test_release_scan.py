"""Release sanitization gate tests."""
from __future__ import annotations

import subprocess
import sys
import tarfile
from pathlib import Path

SCANNER = Path(__file__).parents[2] / "bin" / "scan-release"


def run_scan(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCANNER), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def test_positive_controls_cover_every_rule():
    result = run_scan("--self-test")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "15 classes detected" in result.stdout


def test_clean_tree_passes_and_private_value_is_not_echoed(tmp_path: Path):
    (tmp_path / "clean.txt").write_text("portable release content", encoding="utf-8")
    assert run_scan("--path", str(tmp_path)).returncode == 0

    secret = "AKIA" + "A" * 16
    (tmp_path / "leak.txt").write_text(secret, encoding="utf-8")
    result = run_scan("--path", str(tmp_path))
    assert result.returncode == 1
    assert "aws_access_key" in result.stdout
    assert secret not in result.stdout


def test_archive_content_is_scanned(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "payload.txt").write_text("private" + "@" + "example.com", encoding="utf-8")
    archive = tmp_path / "release.tar"
    with tarfile.open(archive, "w") as output:
        output.add(source, arcname=".")

    result = run_scan("--archive", str(archive))
    assert result.returncode == 1
    assert "email" in result.stdout
