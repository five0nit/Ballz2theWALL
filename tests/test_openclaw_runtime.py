"""OpenClaw local launch contract; no real agent profile or model invocation."""
import json
import subprocess
from unittest.mock import Mock

import pytest

from ballz2thewall.adapters import get_adapter
from ballz2thewall.cli import main


def test_local_native_argv_and_scope(tmp_path):
    adapter = get_adapter("openclaw")
    assert adapter.argv(interactive=False, home=tmp_path) == ["openclaw", "agent", "--local"]
    env = adapter.environment(tmp_path)
    assert env["OPENCLAW_STATE_DIR"] == str(tmp_path)
    assert env["OPENCLAW_CONFIG_PATH"] == str(tmp_path / "openclaw.json")
    assert env["OPENCLAW_OAUTH_DIR"] == str(tmp_path / "credentials")
    assert env["OPENCLAW_AGENT_DIR"] == env["PI_CODING_AGENT_DIR"] == ""


def test_dry_run_omits_prompt(tmp_path, capsys):
    assert main(["run", "openclaw", "--home", str(tmp_path), "--cwd", str(tmp_path),
                 "--prompt", "PRIVATE_TEST_TEXT", "--dry-run"]) == 0
    data = capsys.readouterr().out
    assert "PRIVATE_TEST_TEXT" not in data
    assert "native --message" in data
    assert "--local" in json.loads(data)["argv"]


@pytest.mark.parametrize("key", ["OPENCLAW_STATE_DIR", "OPENCLAW_CONFIG_PATH", "OPENCLAW_OAUTH_DIR",
                                  "OPENCLAW_AGENT_DIR", "PI_CODING_AGENT_DIR", "OPENCLAW_HOME"])
def test_bindings_cannot_redirect_scope(tmp_path, key):
    assert main(["run", "openclaw", "--home", str(tmp_path), "--cwd", str(tmp_path),
                 "--prompt", "test", "--dry-run", "--secret", key + "=env:OTHER"]) == 2


def test_native_launch_is_local_nodelivery_new_session(tmp_path, monkeypatch):
    from ballz2thewall.openclaw_runtime import launch
    runner = Mock(return_value=subprocess.CompletedProcess([], 0))
    monkeypatch.setattr("ballz2thewall.openclaw_runtime.subprocess.run", runner)
    assert launch(["openclaw", "agent", "--local"], "test input", False, tmp_path, {}) == 0
    argv = runner.call_args.args[0]
    assert "--deliver" not in argv
    assert argv[argv.index("--message") + 1] == "test input"
    assert "--session-id" in argv
    assert runner.call_args.kwargs["shell"] is False


def test_native_policy_check_rejects_restrictive_host(tmp_path, monkeypatch):
    from ballz2thewall.openclaw_runtime import verify_native
    payload = {"configPath": str(tmp_path / "openclaw.json"),
               "approvalsPath": str(tmp_path / "exec-approvals.json"),
               "effectivePolicy": {"scopes": [{"host": {"requested": "gateway"},
                   "security": {"effective": "deny"}, "ask": {"effective": "off"}}]}}
    monkeypatch.setattr("ballz2thewall.openclaw_runtime.subprocess.run", Mock(side_effect=[
        subprocess.CompletedProcess([], 0, '{"valid":true}', ''),
        subprocess.CompletedProcess([], 0, json.dumps(payload), '')]))
    with pytest.raises(ValueError, match="effective"):
        verify_native(tmp_path, "openclaw")
