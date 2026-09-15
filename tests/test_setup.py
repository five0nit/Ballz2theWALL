"""Onboarding behavior; native permission APIs are isolated from test accounts."""
import json

import pytest

from ballz2thewall import onboarding
from ballz2thewall.adapters import ADAPTERS
from ballz2thewall.config import parse


def ready(*args, **kwargs):
    return {"status": "ready", "executable": "fixture", "version": "1.2.3"}


def test_enable_disable_exact_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(onboarding, "require_runtime", ready)
    home = tmp_path / "agent"
    home.mkdir()
    original = b'# preserve me\nterminal:\n  backend: local\napprovals:\n  mode: prompt\n'
    (home / "config.yaml").write_bytes(original)
    control = onboarding.Activation(tmp_path / "state")
    result = control.enable("hermes", home)
    assert result["phase"] == "on"
    assert parse((home / "config.yaml").read_bytes(), "config.yaml")["approvals"]["mode"] == "off"
    assert control.enable("hermes", home)["id"] == result["id"]
    assert control.disable()["phase"] == "off"
    assert (home / "config.yaml").read_bytes() == original
    assert control.disable()["phase"] == "off"


def test_no_existing_external_full_access_claim(tmp_path, monkeypatch):
    monkeypatch.setattr(onboarding, "require_runtime", ready)
    home = tmp_path / "agent"
    from ballz2thewall.config import make_plan
    home.mkdir()
    plan = make_plan(ADAPTERS["claude"], home)
    plan.target.write_bytes(plan.after)
    with pytest.raises(ValueError, match="already"):
        onboarding.Activation(tmp_path / "state").enable("claude", home)


def test_off_keeps_later_edits(tmp_path, monkeypatch):
    monkeypatch.setattr(onboarding, "require_runtime", ready)
    home = tmp_path / "agent"
    home.mkdir()
    control = onboarding.Activation(tmp_path / "state")
    control.enable("claude", home)
    (home / "settings.json").write_text('{"new": 42}')
    with pytest.raises(ValueError, match="drift"):
        control.disable()
    assert (home / "settings.json").read_text() == '{"new": 42}'
    assert control.status()["phase"] == "stopping"


def test_switching_agent_requires_off(tmp_path, monkeypatch):
    monkeypatch.setattr(onboarding, "require_runtime", ready)
    control = onboarding.Activation(tmp_path / "state")
    one, two = tmp_path / "one", tmp_path / "two"
    one.mkdir()
    two.mkdir()
    control.enable("claude", one)
    with pytest.raises(ValueError, match="OFF"):
        control.enable("codex", two)
    assert not (two / "config.toml").exists()


def test_interrupted_activation_has_recoverable_own_receipt(tmp_path, monkeypatch):
    monkeypatch.setattr(onboarding, "require_runtime", ready)
    control = onboarding.Activation(tmp_path / "state")
    real_save = control._save
    def fail(record):
        if record["phase"] == "on":
            raise OSError("simulated power loss")
        return real_save(record)
    monkeypatch.setattr(control, "_save", fail)
    home = tmp_path / "agent"
    home.mkdir()
    with pytest.raises(OSError):
        control.enable("claude", home)
    monkeypatch.setattr(control, "_save", real_save)
    assert control.status()["phase"] == "enabling"
    assert control.disable()["phase"] == "off"
    assert not (home / "settings.json").exists()


@pytest.mark.parametrize("data", [[], None, {"phase": "on"}, {"schema": 1, "id": "../../evil", "phase": "on"}])
def test_invalid_activation_is_not_trusted(tmp_path, data):
    control = onboarding.Activation(tmp_path / "state")
    control.root.mkdir(parents=True, mode=0o700)
    control.path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Invalid"):
        control.status()


def test_discovery_selects_exact_home_not_siblings(tmp_path, monkeypatch):
    root = tmp_path / ".hermes"
    (root / "profiles" / "work").mkdir(parents=True)
    (root / "profiles" / "work" / "config.yaml").write_text("{}")
    root.joinpath("config.yaml").write_text("{}")
    monkeypatch.setattr(onboarding.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(onboarding, "inspect_runtime", ready)
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    agents = onboarding.discover_agents()
    assert {a["home"] for a in agents if a["adapter"] == "hermes"} == {str(root), str(root / "profiles" / "work")}
    assert all(a["adapter"] == "hermes" for a in agents)


def test_setup_check_never_requests_permissions(monkeypatch, tmp_path):
    monkeypatch.setattr(onboarding, "discover_agents", lambda: [])
    monkeypatch.setattr(onboarding, "permission_snapshot", lambda: {"platform": "test"})
    result = onboarding.check_setup(tmp_path)
    assert result["permissions"] == {"platform": "test"}
    assert result["activation"]["phase"] == "off"
    assert not tmp_path.joinpath("controller").exists()


def test_dialog_cancel_leaves_config_unchanged(tmp_path, monkeypatch):
    class Cancel:
        def choose(self, *args, **kwargs):
            return None
        def message(self, *args, **kwargs):
            return None
    monkeypatch.setattr(onboarding, "discover_agents", lambda: [{"adapter": "claude", "home": str(tmp_path), "label": "Claude", "status": "ready"}])
    assert onboarding.wizard(tmp_path / "state", dialogs=Cancel()) == 130
    assert not (tmp_path / "settings.json").exists()


def test_windows_snapshot_not_fabricated_admin(monkeypatch):
    result = onboarding.permission_snapshot()
    assert result["platform"] in {"Linux", "Darwin", "Windows"}
    if result["platform"] == "Linux":
        assert result["desktop_permissions"] == "not_managed"


def test_manifest_gui_assets_packaged():
    from importlib.resources import files
    for name in ["dialog.ps1", "dialog.js"]:
        assert files("ballz2thewall").joinpath("native", name).is_file()


def test_on_removed_by_off_new_config(tmp_path, monkeypatch):
    monkeypatch.setattr(onboarding, "require_runtime", ready)
    home = tmp_path / "new"
    home.mkdir()
    control = onboarding.Activation(tmp_path / "state")
    control.enable("codex", home)
    control.disable()
    assert not (home / "config.toml").exists()
