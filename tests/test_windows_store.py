"""Real Windows-only security/locking gates, plus platform-neutral regression tests."""
from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from ballz2thewall import platform_store
from ballz2thewall.config import Plan
from ballz2thewall.store import Store, atomic_write, read_optional

native_windows = pytest.mark.skipif(sys.platform != "win32", reason="requires native Windows ACL/locking APIs")


def test_store_round_trip_bytes_and_absence(tmp_path):
    store = Store(tmp_path / "state")
    target = tmp_path / "home" / "config.json"
    for before in (None, b'{"untouched":"original"}\r\n'):
        if before is not None:
            target.parent.mkdir(exist_ok=True)
            target.write_bytes(before)
        plan = Plan(target, before, b'{"enabled":true}\n', {}, "test")
        result = store.apply(plan)
        assert target.read_bytes() == plan.after
        assert store.apply(Plan(target, plan.after, plan.after, {}, "test"))["status"] == "unchanged"
        assert Store(store.root).rollback(result["receipt_id"])["status"] == "rolled_back"
        assert read_optional(target) == before
        assert store.rollback(result["receipt_id"])["status"] == "already_rolled_back"


def test_atomic_failure_cleans_temp_and_preserves_target(tmp_path, monkeypatch):
    target = tmp_path / "config"
    target.write_bytes(b"original")

    def fail(*args):
        raise OSError("replacement failed")

    monkeypatch.setattr(platform_store, "replace_file", fail)
    with pytest.raises(OSError, match="replacement failed"):
        atomic_write(target, b"new")
    assert target.read_bytes() == b"original"
    assert not list(tmp_path.glob(".ballz-*"))


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX mode contract")
def test_posix_permissions_still_enforced(tmp_path):
    root = tmp_path / "state"
    root.mkdir(mode=0o755)
    root.chmod(0o755)
    with pytest.raises(ValueError, match="0700"):
        with Store(root).lock():
            pass
    root.chmod(0o700)
    with Store(root).lock():
        pass
    target = tmp_path / "config"
    atomic_write(target, b"private", mode=0o640)
    assert stat.S_IMODE(target.stat().st_mode) == 0o640


@native_windows
def test_windows_acl_and_reparse_security(tmp_path):
    # This script performs independent native subprocess lock/ACL/junction tests.
    script = Path(__file__).resolve().parents[1] / "scripts" / "windows_store_smoke.py"
    result = subprocess.run([sys.executable, str(script), "--scratch-parent", str(tmp_path)],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"status": "passed"' in result.stdout


@native_windows
def test_windows_atomic_write_does_not_use_posix_calls(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("POSIX-only primitive used on Windows")

    monkeypatch.setattr(os, "fchmod", forbidden, raising=False)
    target = tmp_path / "config"
    atomic_write(target, b"first")
    atomic_write(target, b"second")
    assert target.read_bytes() == b"second"
    platform_store.sync_dir(tmp_path)
