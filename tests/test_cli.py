import json
from unittest.mock import Mock

import pytest

from ballz2thewall import cli
from ballz2thewall.adapters import get_adapter
from ballz2thewall.doctor import inspect_runtime


def test_plan_does_not_create_home_or_state(tmp_path, capsys):
    home = tmp_path / "not-created"
    assert cli.main(["plan", "hermes", "--home", str(home)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["settings"]["approvals.mode"] == "off"
    assert not home.exists()


def test_cli_apply_rollback_roundtrip(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "require_runtime", lambda *a: {"status": "ready"})
    home, state = tmp_path / "home", tmp_path / "state"
    assert cli.main(["apply", "hermes", "--home", str(home), "--state-dir", str(state)]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert cli.main(["rollback", receipt["receipt_id"], "--state-dir", str(state)]) == 0
    assert not (home / "config.yaml").exists()


def test_run_dry_resolves_no_secrets(tmp_path, monkeypatch, capsys):
    import ballz2thewall.credentials as creds
    def forbidden(*args, **kwargs):
        pytest.fail("Must not resolve credentials during dry run")
    monkeypatch.setattr(creds, "resolve_bindings", forbidden)
    args = ["run", "hermes", "--home", str(tmp_path), "--cwd", str(tmp_path),
            "--prompt", "NEVER_PRINT_PROMPT", "--dry-run", "--secret", "API_KEY=env:NOT_SET"]
    assert cli.main(args) == 0
    text = capsys.readouterr().out
    assert "NEVER_PRINT_PROMPT" not in text
    assert json.loads(text)["status"] == "dry_run"


def test_native_process_stdin_env_and_exit(tmp_path, monkeypatch, capfd):
    import sys
    script = tmp_path / "runtime"
    script.write_text(f"#!{sys.executable}\n" +
        "import os,sys,json\n" +
        "print(json.dumps({'stdin':sys.stdin.read(),'args':sys.argv[1:],'scope':os.environ.get('HERMES_HOME'),'bound':os.environ.get('BOUND')}))\n" +
        "sys.exit(7)\n")
    script.chmod(0o700)
    monkeypatch.setattr(cli, "require_runtime", lambda *a: {"executable": str(script)})
    monkeypatch.setenv("BALLZ_TEST_VALUE", "explicit-test-value")
    prompt = "a; $(touch SHOULD_NOT_EXIST) ' \" --help"
    assert cli.main(["run", "hermes", "--home", str(tmp_path), "--cwd", str(tmp_path),
                     "--prompt", prompt, "--secret", "BOUND=env:BALLZ_TEST_VALUE"]) == 7
    result = json.loads(capfd.readouterr().out)
    assert result["stdin"] == prompt
    assert prompt not in result["args"]
    assert result["scope"] == str(tmp_path)
    assert result["bound"] == "explicit-test-value"
    assert not (tmp_path / "SHOULD_NOT_EXIST").exists()


def test_scope_override_rejected(tmp_path, capsys):
    assert cli.main(["run", "hermes", "--home", str(tmp_path), "--cwd", str(tmp_path),
                     "--prompt", "test", "--dry-run", "--secret", "HERMES_HOME=env:HOME"]) == 2
    assert "cannot replace" in capsys.readouterr().out


def test_skill_install_and_rollback(tmp_path, capsys):
    root, state = tmp_path / "skills", tmp_path / "state"
    assert cli.main(["skill", "--dest", str(root), "--state-dir", str(state)]) == 0
    receipt = json.loads(capsys.readouterr().out)
    content = (root / "ballz2thewall/SKILL.md").read_text()
    assert "name: ballz2thewall" in content
    assert cli.main(["rollback", receipt["receipt_id"], "--state-dir", str(state)]) == 0
    assert not (root / "ballz2thewall/SKILL.md").exists()


def test_doctor_missing(monkeypatch):
    monkeypatch.setattr("ballz2thewall.doctor.shutil.which", lambda _: None)
    assert inspect_runtime(get_adapter("hermes"))["status"] == "missing"


def test_doctor_unsupported(monkeypatch):
    monkeypatch.setattr("ballz2thewall.doctor.shutil.which", lambda _: "/fake")
    monkeypatch.setattr("ballz2thewall.doctor.subprocess.run", lambda *a, **kw: Mock(returncode=0, stdout="0.0.1"))
    assert inspect_runtime(get_adapter("hermes"))["status"] == "unsupported"


def test_home_required():
    with pytest.raises(SystemExit) as caught:
        cli.main(["apply", "hermes"])
    assert caught.value.code == 2


def test_malformed_secret_does_not_echo(tmp_path, capsys):
    assert cli.main(["run", "hermes", "--home", str(tmp_path), "--cwd", str(tmp_path),
                    "--dry-run", "--prompt", "x", "--secret", "TEST_RAW_PASSWORD"]) == 2
    assert "TEST_RAW_PASSWORD" not in capsys.readouterr().out
