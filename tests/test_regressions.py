"""Regressions found by native-contract and release-gate checks."""
import json
from unittest.mock import Mock

import pytest

from ballz2thewall import cli
from ballz2thewall.adapters import get_adapter
from ballz2thewall.doctor import inspect_runtime


@pytest.mark.parametrize("name,text,version", [
    ("hermes", "Hermes Agent v0.21.1 (2026.9.7)\nPython: 3.11.15", "0.21.1"),
    ("codex", "codex-cli 0.152.0", "0.152.0"),
    ("claude", "2.1.201 (Claude Code)", "2.1.201"),
])
def test_doctor_native_version(name, text, version, monkeypatch):
    adapter = get_adapter(name)
    monkeypatch.setattr("ballz2thewall.doctor.shutil.which", lambda _: "/fake")
    monkeypatch.setattr("ballz2thewall.doctor.subprocess.run", lambda argv, **kw:
                        Mock(returncode=0, stdout=text if "--version" in argv else adapter.flag))
    report = inspect_runtime(adapter)
    assert report["version"] == version
    assert report["version_match"]


@pytest.mark.parametrize("setting", ["backend: docker", "backend: ssh", "cwd: /other/workspace"])
def test_run_rejects_conflicting_hermes_terminal(tmp_path, capsys, setting):
    (tmp_path / "config.yaml").write_text(f"terminal:\n  {setting}\n")
    assert cli.main(["run", "hermes", "--home", str(tmp_path), "--cwd", str(tmp_path),
                     "--prompt", "x", "--dry-run"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "error"


@pytest.mark.parametrize("cwd", [".", "auto", "cwd"])
def test_run_accepts_dynamic_hermes_cwd(tmp_path, capsys, cwd):
    (tmp_path / "config.yaml").write_text(f"terminal:\n  backend: local\n  cwd: {cwd}\n")
    assert cli.main(["run", "hermes", "--home", str(tmp_path), "--cwd", str(tmp_path),
                     "--prompt", "x", "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["cwd"] == str(tmp_path)
