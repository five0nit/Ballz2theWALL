"""Installer readiness is dependency evidence, never OS consent or activation."""
import json
import subprocess
from unittest.mock import Mock

import pytest

from ballz2thewall import cli, onboarding


def test_check_cli_does_not_read_or_create_activation(tmp_path, capsys):
    state = tmp_path / "untouched"
    assert cli.main(["machine", "check", "--state-dir", str(state)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "ready"
    assert result["scope"] == "dependencies_and_native_executable_only"
    assert result["live_permissions"] == "not_tested"
    assert result["desktop_driver"]["version"] == "cua-driver 0.28.1"
    assert not state.exists()


@pytest.fixture
def checked(monkeypatch):
    from ballz2thewall import machine_check as check
    monkeypatch.setattr(check, "version", lambda name: {"mcp": "1.30.0", "cua-driver": "0.28.1"}[name])
    monkeypatch.setattr(check, "import_module", lambda name: object())
    monkeypatch.setattr(check, "desktop_spec", lambda: {"command": "/fixture/cua-driver", "env": {"PRIVATE": "not printed"}})
    monkeypatch.setattr(check.subprocess, "run", Mock(return_value=subprocess.CompletedProcess([], 0, "cua-driver 0.28.1\n", "")))
    return check


def test_ready_does_not_echo_environment(checked):
    result = checked.inspect_machine()
    assert result["status"] == "ready"
    assert "PRIVATE" not in json.dumps(result)
    assert checked.subprocess.run.call_args.args[0] == ["/fixture/cua-driver", "--version"]
    assert checked.subprocess.run.call_args.kwargs["timeout"] == 10


@pytest.mark.parametrize("name", ["mcp", "cua-driver"])
def test_missing_package(checked, monkeypatch, name):
    original = checked.version
    def missing(package):
        if package == name:
            raise checked.PackageNotFoundError(package)
        return original(package)
    monkeypatch.setattr(checked, "version", missing)
    result = checked.inspect_machine()
    assert result["status"] == "unavailable"
    assert result["packages"][name]["installed"] is None
    assert result["errors"]


@pytest.mark.parametrize("name", ["mcp", "cua-driver"])
def test_wrong_version(checked, monkeypatch, name):
    original = checked.version
    monkeypatch.setattr(checked, "version", lambda package: "0.0.0" if package == name else original(package))
    assert checked.inspect_machine()["status"] == "unavailable"


@pytest.mark.parametrize("error", [ImportError("transitive dependency"), OSError("DLL missing")])
def test_broken_import(checked, monkeypatch, error):
    monkeypatch.setattr(checked, "import_module", Mock(side_effect=error))
    assert checked.inspect_machine()["status"] == "unavailable"


@pytest.mark.parametrize("error", [ValueError("no driver"), OSError("not executable"), subprocess.TimeoutExpired("driver", 10)])
def test_unavailable_native_binary(checked, monkeypatch, error):
    monkeypatch.setattr(checked, "desktop_spec", Mock(side_effect=error))
    assert checked.inspect_machine()["status"] == "unavailable"


@pytest.mark.parametrize("code,text", [(1, "cua-driver 0.28.1"), (0, "cua-driver 0.28.0"), (0, ""), (0, "some executable 0.28.1")])
def test_driver_result_must_be_real_expected_version(checked, monkeypatch, code, text):
    monkeypatch.setattr(checked.subprocess, "run", Mock(return_value=subprocess.CompletedProcess([], code, text, "")))
    assert checked.inspect_machine()["status"] == "unavailable"


def test_cli_unavailable_is_json_exit_two(checked, monkeypatch, capsys):
    monkeypatch.setattr(checked, "inspect_machine", lambda: {"status": "unavailable", "errors": ["missing"]})
    assert cli.main(["machine", "check"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "unavailable"


def test_wizard_stops_before_permissions_and_profile_writes(checked, monkeypatch, tmp_path):
    monkeypatch.setattr(onboarding, "discover_agents", lambda: [{"adapter": "hermes", "home": str(tmp_path), "label": "Hermes"}])
    monkeypatch.setattr(checked, "inspect_machine", lambda: {"status": "unavailable", "errors": ["missing"]})
    permissions = Mock(side_effect=AssertionError("Permission flow must not run"))
    monkeypatch.setattr(onboarding, "permission_snapshot", permissions)
    dialogs = Mock()
    state = tmp_path / "state"
    assert onboarding.wizard(state, dialogs) == 2
    assert "reinstall" in dialogs.message.call_args.args[1].lower()
    assert not state.exists()


def test_failed_cli_on_does_not_activate(checked, monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(checked, "inspect_machine", lambda: {"status": "unavailable", "errors": ["missing"]})
    enable = Mock(side_effect=AssertionError("must not activate"))
    monkeypatch.setattr(onboarding.Activation, "enable", enable)
    assert cli.main(["on", "hermes", "--home", str(tmp_path), "--state-dir", str(tmp_path / "state")]) == 2
    assert "reinstall" in json.loads(capsys.readouterr().out)["error"].lower()
    enable.assert_not_called()
