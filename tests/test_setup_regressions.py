import json

import pytest

from ballz2thewall import onboarding as ob


def ready(*args, **kwargs):
    return {"status": "ready", "executable": "fixture", "version": "1.0"}


@pytest.mark.parametrize("field,bad", [("phase", []), ("adapter", []), ("after_sha256", None), ("receipt_id", []), ("schema", True)])
def test_malformed_activation_is_explicit_error(tmp_path, monkeypatch, field, bad):
    monkeypatch.setattr(ob, "require_runtime", ready)
    home = tmp_path / "home"
    home.mkdir()
    ctl = ob.Activation(tmp_path / "state")
    ctl.enable("claude", home)
    record = json.loads(ctl.path.read_text())
    record[field] = bad
    ctl.path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="Invalid activation"):
        ctl.status()


def test_missing_receipt_never_claims_off(tmp_path, monkeypatch):
    monkeypatch.setattr(ob, "require_runtime", ready)
    home = tmp_path / "home"
    home.mkdir()
    ctl = ob.Activation(tmp_path / "state")
    active = ctl.enable("claude", home)
    receipt = ctl.root / "activations" / active["id"] / (active["receipt_id"] + ".json")
    receipt.unlink()
    with pytest.raises(ValueError, match="receipt missing"):
        ctl.disable()
    assert ctl.status()["phase"] == "stopping"
    assert (home / "settings.json").exists()


def test_native_dialog_resources_packaged():
    root = ob.files("ballz2thewall").joinpath("native")
    assert root.joinpath("dialog.ps1").is_file()
    assert root.joinpath("dialog.js").is_file()


def test_mac_uses_one_managed_python_setting():
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "installers/Install-Mac.command"
    if not path.exists():
        pytest.skip("source installer asset tested separately from immutable wheel")
    source = path.read_text()
    assert "unset UV_PYTHON_PREFERENCE" in source
    assert "--managed-python" in source
    assert "--reinstall-package ballz2thewall" in source
