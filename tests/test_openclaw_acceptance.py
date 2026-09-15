"""Integration regressions around native OpenClaw activation and scope."""
import json
from unittest.mock import Mock

import pytest

from ballz2thewall.adapters import get_adapter
from ballz2thewall.onboarding import Activation
from ballz2thewall.openclaw import make_plans
from ballz2thewall.openclaw_runtime import inspect_native


@pytest.mark.parametrize("runtime", [{"type":"acp","acp":{"agent":"codex"}},
                                      {"type":"embedded"}, {}, "acp", False])
def test_explicit_agent_runtime_rejected_before_write(tmp_path, runtime):
    home=tmp_path / ".openclaw"
    home.mkdir()
    config=home / "openclaw.json"
    before=json.dumps({"agents":{"list":[{"id":"main","runtime":runtime}]}}).encode()
    config.write_bytes(before)
    with pytest.raises(ValueError,match="runtime overrides"):
        make_plans(home)
    assert config.read_bytes()==before
    assert not (home / "exec-approvals.json").exists()


def test_unsupported_layout_never_probes_native(tmp_path,monkeypatch):
    child=Mock(side_effect=AssertionError("must not spawn"))
    monkeypatch.setattr("ballz2thewall.openclaw_runtime.subprocess.run",child)
    assert inspect_native(get_adapter("openclaw"),tmp_path / "named-profile")["status"] != "ready"
    child.assert_not_called()


def test_failed_native_verification_compensates_both_files(tmp_path,monkeypatch):
    home=tmp_path / ".openclaw"
    home.mkdir()
    originals={"openclaw.json":b"{ /* preserve exact comments */ }\n",
               "exec-approvals.json":b'{"version":1,"defaults":{"security":"deny"}}\n'}
    for name,content in originals.items():
        (home / name).write_bytes(content)
    monkeypatch.setattr("ballz2thewall.onboarding.require_runtime",lambda *args:{"executable":"unused"})
    monkeypatch.setattr("ballz2thewall.openclaw_runtime.verify_native",Mock(side_effect=ValueError("native mismatch")))
    control=Activation(tmp_path / "state")
    with pytest.raises(ValueError):
        control.enable("openclaw",home)
    assert {p:(home/p).read_bytes() for p in originals}==originals
    assert control.status()["phase"] != "on"
    assert control.disable()["phase"] == "off"
