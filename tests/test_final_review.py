"""Bounded final-review regressions for launch scope and malformed receipts."""
import json

import pytest

from ballz2thewall import cli
from ballz2thewall.config import parse


def test_hermes_inherited_terminal_cwd_is_pinned(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TERMINAL_CWD", "/unrelated/parent/workspace")
    assert cli.main(["run", "hermes", "--home", str(tmp_path), "--cwd", str(tmp_path),
                     "--prompt", "x", "--dry-run"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["environment_overrides"]["TERMINAL_CWD"] == str(tmp_path)


def test_hermes_relative_config_cwd_resolves_in_child(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    workspace = tmp_path / "child"
    workspace.mkdir()
    (tmp_path / "config.yaml").write_text("terminal:\n  cwd: child\n")
    assert cli.main(["run", "hermes", "--home", str(tmp_path), "--cwd", str(workspace),
                     "--prompt", "x", "--dry-run"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "error"


@pytest.mark.parametrize("value", ["null", "1", "true", "[]"])
def test_hermes_non_string_cwd_rejected(tmp_path, capsys, value):
    (tmp_path / "config.yaml").write_text(f"terminal:\n  cwd: {value}\n")
    assert cli.main(["run", "hermes", "--home", str(tmp_path), "--cwd", str(tmp_path),
                     "--prompt", "x", "--dry-run"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "error"


@pytest.mark.parametrize("record", [[], None, {"schema": 1, "id": "a" * 32, "status": []},
                                    {"schema": 1, "id": "a" * 32, "status": "applied"},
                                    {"schema": 1, "id": "a" * 32, "status": "prepared", "target": 7}])
def test_malformed_receipt_is_clean_cli_error(tmp_path, capsys, record):
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    (state / ("a" * 32 + ".json")).write_text(json.dumps(record))
    assert cli.main(["rollback", "a" * 32, "--state-dir", str(state)]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "error"


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_json_nonstandard_constant_rejected(constant):
    with pytest.raises(ValueError, match="Invalid native config"):
        parse(('{"unrelated":' + constant + '}').encode(), "settings.json")
