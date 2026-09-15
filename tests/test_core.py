import json
import os
import stat
from pathlib import Path

import pytest

from ballz2thewall.adapters import ADAPTERS, get_adapter
from ballz2thewall.config import make_plan, parse
from ballz2thewall.platform_store import validate_state_files
from ballz2thewall.store import Store, digest


@pytest.mark.parametrize("name", [n for n in ADAPTERS if n != "openclaw"])
def test_apply_idempotent_rollback_exact_bytes(tmp_path, name):
    a = get_adapter(name)
    home = tmp_path / "home"
    home.mkdir()
    originals = {
        "hermes": b"# preserve on rollback\nmodel:\n  default: existing\n  api_key: TEST_ONLY_SENTINEL\napprovals:\n  deny: ['git push --force*']\n",
        "codex": b'# keep TOML comment\nmodel = "existing"\n[custom]\nkey = "TEST_ONLY_SENTINEL"\n',
        "claude": b'{"model":"existing","env":{"KEY":"TEST_ONLY_SENTINEL"},"permissions":{"deny":["Read(.env)"]}}',
    }
    target = home / a.filename
    target.write_bytes(originals[name])
    target.chmod(0o640)
    original_mode = stat.S_IMODE(target.stat().st_mode)
    plan = make_plan(a, home)
    assert "TEST_ONLY_SENTINEL" not in json.dumps(plan.public())
    result = Store(tmp_path / "state").apply(plan)
    parsed = parse(target.read_bytes(), a.filename)
    assert parsed["model"] == ({"default": "existing", "api_key": "TEST_ONLY_SENTINEL"} if name == "hermes" else "existing")
    if name == "hermes":
        assert parsed["approvals"]["mode"] == "off"
        assert parsed["approvals"]["deny"] == ['git push --force*']
    if name == "claude":
        assert parsed["permissions"]["deny"] == ["Read(.env)"]
    assert stat.S_IMODE(target.stat().st_mode) == original_mode
    assert Store(tmp_path / "state").apply(make_plan(a, home))["status"] == "unchanged"
    record = Path(result["receipt"]).read_text()
    assert "TEST_ONLY_SENTINEL" not in record
    if os.name == "nt":
        validate_state_files(tmp_path / "state")  # Native owner-only ACL, not POSIX mode bits.
    else:
        assert stat.S_IMODE(Path(result["receipt"]).stat().st_mode) == 0o600
    assert Store(tmp_path / "state").rollback(result["receipt_id"])["status"] == "rolled_back"
    assert target.read_bytes() == originals[name]
    assert stat.S_IMODE(target.stat().st_mode) == original_mode
    assert Store(tmp_path / "state").rollback(result["receipt_id"])["status"] == "already_rolled_back"


@pytest.mark.parametrize("name", [n for n in ADAPTERS if n != "openclaw"])
def test_new_file_removed_on_rollback(tmp_path, name):
    a = get_adapter(name)
    home = tmp_path / "new-home"
    state = Store(tmp_path / "state")
    receipt = state.apply(make_plan(a, home))
    assert (home / a.filename).exists()
    state.rollback(receipt["receipt_id"])
    assert not (home / a.filename).exists()


def test_drift_not_overwritten(tmp_path):
    home = tmp_path / "home"
    state = Store(tmp_path / "state")
    plan = make_plan(get_adapter("hermes"), home)
    receipt = state.apply(plan)
    plan.target.write_text("model: edited\n")
    with pytest.raises(ValueError, match="drift"):
        state.rollback(receipt["receipt_id"])
    assert plan.target.read_text() == "model: edited\n"


def test_stale_plan_rejected(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    plan = make_plan(get_adapter("hermes"), home)
    plan.target.write_text("model: new\n")
    with pytest.raises(ValueError, match="after planning"):
        Store(tmp_path / "state").apply(plan)


def test_corrupt_backup_rejected(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.yaml").write_text("model: before\n")
    state = Store(tmp_path / "state")
    result = state.apply(make_plan(get_adapter("hermes"), home))
    (state.root / f"{result['receipt_id']}.before").write_text("changed")
    with pytest.raises(ValueError, match="corrupted"):
        state.rollback(result["receipt_id"])


@pytest.mark.parametrize("data,filename", [
    (b"- x", "config.yaml"), (b"[]", "settings.json"), (b"[", "config.toml"),
    (b"a: 1\na: 2", "config.yaml"), (b'{"a":1,"a":2}', "settings.json"),
    (b'key="TEST_ONLY_SENTINEL', "config.toml"), (b"!!python/object/apply:os.system []", "config.yaml"),
    (b"\xff", "config.yaml"),
])
def test_invalid_config_has_redacted_error(data, filename):
    with pytest.raises(ValueError) as caught:
        parse(data, filename)
    assert "TEST_ONLY_SENTINEL" not in str(caught.value)


def test_conflicting_section_rejected(tmp_path):
    (tmp_path / "config.yaml").write_text("approvals: false\n")
    with pytest.raises(ValueError, match="not a mapping"):
        make_plan(get_adapter("hermes"), tmp_path)


def test_new_codex_permission_profile_conflict(tmp_path):
    (tmp_path / "config.toml").write_text('default_permissions = ":workspace"\n')
    with pytest.raises(ValueError, match="default_permissions"):
        make_plan(get_adapter("codex"), tmp_path)


def test_symlink_rejected(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    target = tmp_path / "other"
    target.write_text("model: before\n")
    (home / "config.yaml").symlink_to(target)
    with pytest.raises(ValueError, match="symlink"):
        make_plan(get_adapter("hermes"), home)
    assert target.read_text() == "model: before\n"


def test_symlink_parent_rejected(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    link = tmp_path / "link"
    link.symlink_to(home, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        make_plan(get_adapter("hermes"), link)


def test_receipt_id_validation(tmp_path):
    with pytest.raises(ValueError, match="Receipt ID"):
        Store(tmp_path / "state").rollback("../../elsewhere")


def test_prepared_receipt_recovers_after_write(tmp_path):
    state = Store(tmp_path / "state")
    result = state.apply(make_plan(get_adapter("hermes"), tmp_path / "home"))
    file = Path(result["receipt"])
    data = json.loads(file.read_text())
    data["status"] = "prepared"
    file.write_text(json.dumps(data))
    assert state.rollback(result["receipt_id"])["status"] == "rolled_back"


def test_toml_comment_retained(tmp_path):
    (tmp_path / "config.toml").write_text('# keep this comment\nmodel = "existing"\n')
    plan = make_plan(get_adapter("codex"), tmp_path)
    assert b"# keep this comment" in plan.after


def test_unrelated_homes_untouched(tmp_path):
    active = tmp_path / "active"
    active.mkdir()
    target = active / "config.yaml"
    target.write_text("model: KEEP\n")
    Store(tmp_path / "state").apply(make_plan(get_adapter("hermes"), tmp_path / "isolated"))
    assert target.read_text() == "model: KEEP\n"


@pytest.mark.parametrize("name,flag", [(a.name, a.flag) for a in ADAPTERS.values()])
def test_argv_contract(name, flag):
    a = get_adapter(name)
    assert flag in a.argv(interactive=False)
    assert flag in a.argv(interactive=True)
    assert a.environment(Path("/explicit"))[a.home_env] == str(Path("/explicit"))


def test_aliases_and_options():
    assert get_adapter("openai") == get_adapter("codex")
    assert get_adapter("anthropic") == get_adapter("claude")
    with pytest.raises(ValueError):
        get_adapter("missing")
    with pytest.raises(ValueError):
        get_adapter("codex").settings(cdp="http://localhost:9222")
    with pytest.raises(ValueError):
        get_adapter("hermes").argv(interactive=True, chrome=True)
    assert get_adapter("codex").settings(inherit_secrets=True)["shell_environment_policy.ignore_default_excludes"]
    assert "--chrome" in get_adapter("claude").argv(interactive=True, chrome=True)


def test_digest_none_and_bytes():
    assert digest(None) is None
    assert len(digest(b"")) == 64
