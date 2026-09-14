"""Late review regressions; temporary configs only, no native auth or model calls."""

import json
from pathlib import Path

import pytest

from ballz2thewall import cli
from ballz2thewall.adapters import get_adapter
from ballz2thewall.config import make_plan
from ballz2thewall.store import Store


@pytest.mark.parametrize("named", [False, True])
def test_explicit_home_ignores_sticky_profile(tmp_path, capsys, named):
    home = tmp_path / "selected"
    if named:
        home = home / "profiles" / "chosen"
    (home / "profiles" / "other").mkdir(parents=True)
    marker = home / "active_profile"
    marker.write_text("other\n")
    assert (
        cli.main(
            ["run", "hermes", "--home", str(home), "--cwd", str(tmp_path), "--prompt", "test", "--dry-run"]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["environment_overrides"]["HERMES_HOME"] == str(home)
    # Hermes trusts profile-shaped homes. Other roots need explicit default selection.
    if named:
        assert "--profile" not in result["argv"]
    else:
        assert result["argv"][1:3] == ["--profile", "default"]
    assert marker.read_text() == "other\n"


@pytest.mark.parametrize(
    "terminal,code",
    [
        ({"env_type": "docker"}, 2),
        ({"env_type": "ssh"}, 2),
        ({"backend": "local", "env_type": "docker"}, 0),
        ({"backend": "docker", "env_type": "local"}, 2),
        ({"env_type": "local", "cwd": "/stored/messaging/workspace"}, 0),
        ({"backend": "local", "cwd": "child"}, 0),
    ],
)
def test_native_terminal_precedence(tmp_path, capsys, terminal, code):
    target = tmp_path / "config.yaml"
    original = json.dumps({"terminal": terminal})
    target.write_text(original)
    assert (
        cli.main(
            [
                "run",
                "hermes",
                "--home",
                str(tmp_path),
                "--cwd",
                str(tmp_path),
                "--prompt",
                "test",
                "--dry-run",
            ]
        )
        == code
    )
    result = json.loads(capsys.readouterr().out)
    if code == 0:
        assert result["environment_overrides"]["TERMINAL_CWD"] == str(tmp_path)
        assert result["environment_overrides"]["TERMINAL_ENV"] == "local"
    else:
        assert result["status"] == "error"
    assert target.read_text() == original


@pytest.mark.parametrize("exists", [False, True])
@pytest.mark.parametrize(
    "stage",
    [
        "intent_before",
        "intent_after",
        "restore_before",
        "restore_after",
        "completion_before",
        "completion_after",
    ],
)
def test_interrupted_rollback_retries(tmp_path, monkeypatch, exists, stage):
    import ballz2thewall.store as module

    home = tmp_path / "home"
    home.mkdir()
    target = home / "config.yaml"
    original = b"# restore exact bytes\nmodel: existing\n" if exists else None
    if exists:
        target.write_bytes(original)
        target.chmod(0o640)
    state = Store(tmp_path / "state")
    receipt = state.apply(make_plan(get_adapter("hermes"), home))
    save, write, unlink = Store._save, module.atomic_write, Path.unlink
    fired = []

    def interrupt():
        fired.append(stage)
        raise OSError("injected rollback interruption")

    def faulty_save(self, record):
        phase = {"rolling_back": "intent", "rolled_back": "completion"}.get(record["status"])
        if stage == f"{phase}_before":
            interrupt()
        save(self, record)
        if stage == f"{phase}_after":
            interrupt()

    def faulty_write(path, data, mode=0o600):
        if path == target and stage == "restore_before":
            interrupt()
        write(path, data, mode)
        if path == target and stage == "restore_after":
            interrupt()

    def faulty_unlink(path, *args, **kwargs):
        if path == target and stage == "restore_before":
            interrupt()
        unlink(path, *args, **kwargs)
        if path == target and stage == "restore_after":
            interrupt()

    with monkeypatch.context() as patcher:
        patcher.setattr(Store, "_save", faulty_save)
        patcher.setattr(module, "atomic_write", faulty_write)
        patcher.setattr(Path, "unlink", faulty_unlink)
        with pytest.raises(OSError, match="injected"):
            state.rollback(receipt["receipt_id"])
    assert fired == [stage]
    # Fresh Store simulates restart: no in-memory recovery state available.
    result = Store(state.root).rollback(receipt["receipt_id"])
    assert result["status"] in {"rolled_back", "already_rolled_back"}
    assert (target.read_bytes() if target.exists() else None) == original
    if exists:
        assert target.stat().st_mode & 0o777 == 0o640
    assert json.loads(Path(receipt["receipt"]).read_text())["status"] == "rolled_back"
    assert state.rollback(receipt["receipt_id"])["status"] == "already_rolled_back"


@pytest.mark.parametrize("exists", [False, True])
def test_legacy_interrupted_rollback_acknowledges_restored_bytes(tmp_path, exists):
    home = tmp_path / "home"
    home.mkdir()
    target = home / "config.yaml"
    original = b"model: original\n" if exists else None
    if exists:
        target.write_bytes(original)
    state = Store(tmp_path / "state")
    receipt = state.apply(make_plan(get_adapter("hermes"), home))
    # v0.1.0 could restore bytes without persisting the final receipt status.
    if exists:
        target.write_bytes(original)
    else:
        target.unlink()
    assert state.rollback(receipt["receipt_id"])["status"] == "rolled_back"
    assert (target.read_bytes() if target.exists() else None) == original


@pytest.mark.parametrize("kind", ["default", "nested", "named"])
def test_scope_under_platform_home(tmp_path, monkeypatch, capsys, kind):
    monkeypatch.setenv("HOME", str(tmp_path))
    default = tmp_path / ".hermes"
    home = {"default": default, "nested": default / "staging", "named": default / "profiles" / "chosen"}[kind]
    home.mkdir(parents=True)
    result = cli.main(
        ["run", "hermes", "--home", str(home), "--cwd", str(tmp_path), "--prompt", "test", "--dry-run"]
    )
    data = json.loads(capsys.readouterr().out)
    assert result == 0
    if kind != "named":
        assert data["argv"][1:3] == ["--profile", "default"]
    else:
        assert "--profile" not in data["argv"]


def test_doctor_pins_selected_home(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from ballz2thewall import doctor

    calls = []
    monkeypatch.setattr(doctor.shutil, "which", lambda _: "/fixture/hermes")

    def capture(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout="--yolo 0.21.1")

    monkeypatch.setattr(doctor.subprocess, "run", capture)
    assert doctor.inspect_runtime(get_adapter("hermes"), tmp_path)["status"] == "ready"
    assert len(calls) == 2
    for argv, kwargs in calls:
        assert argv[1:3] == ["--profile", "default"]
        assert kwargs["env"]["HERMES_HOME"] == str(tmp_path)


def test_rollback_rechecks_drift_after_intent(tmp_path, monkeypatch):
    state = Store(tmp_path / "state")
    receipt = state.apply(make_plan(get_adapter("hermes"), tmp_path / "home"))
    target = Path(receipt["target"])
    save = Store._save

    def concurrent_edit(self, record):
        save(self, record)
        if record["status"] == "rolling_back":
            target.write_bytes(b"model: concurrent-edit\n")

    monkeypatch.setattr(Store, "_save", concurrent_edit)
    with pytest.raises(ValueError, match="drift"):
        state.rollback(receipt["receipt_id"])
    assert target.read_bytes() == b"model: concurrent-edit\n"
    monkeypatch.setattr(Store, "_save", save)
    with pytest.raises(ValueError, match="drift"):
        Store(state.root).rollback(receipt["receipt_id"])
