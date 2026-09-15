"""OpenClaw planning and journal recovery use scratch homes only."""
import json
from pathlib import Path

import pytest

from ballz2thewall.openclaw import OpenClawStore, make_plans, parse_config
from ballz2thewall.store import Store


@pytest.fixture
def home(tmp_path):
    path = tmp_path / "native"
    path.mkdir()
    (path / "openclaw.json").write_bytes(
        b"// original comment\n{channels: {telegram: {token: '${BOT_TOKEN}'}}, "
        b"agents: {list: [{id: 'main', name: 'Keep me'}]}, "
        b"models: {providers: {custom: {apiKey: 'fixture-secret'}}}}\n"
    )
    return path


def bundle(store):
    paths = list(store.root.glob("*.bundle.json"))
    assert len(paths) == 1
    return paths[0], json.loads(paths[0].read_bytes())


def test_policy_preserves_unrelated_values_and_exact_rollback(home, tmp_path):
    original = (home / "openclaw.json").read_bytes()
    approvals = b'{"version":1,"socket":{"token":"fixture-socket"},"agents":{"main":{"allowlist":[{"pattern":"pwd"}]}}}'
    (home / "exec-approvals.json").write_bytes(approvals)
    plans = make_plans(home)
    assert len(plans) == 2
    config = parse_config(plans[0].after)
    assert config["channels"]["telegram"]["token"] == "${BOT_TOKEN}"
    assert config["models"]["providers"]["custom"]["apiKey"] == "fixture-secret"
    assert config["agents"]["defaults"]["sandbox"]["mode"] == "off"
    for tools in (config["tools"], config["agents"]["list"][0]["tools"]):
        assert tools["profile"] == "full"
        assert tools["allow"] == ["*"]
        assert tools["deny"] == []
        assert tools["exec"]["host"] == "gateway"
        assert tools["exec"]["mode"] == "full"
        assert "security" not in tools["exec"]
        assert "ask" not in tools["exec"]
        assert tools["exec"]["strictInlineEval"] is False
        assert tools["exec"]["applyPatch"]["workspaceOnly"] is False
        assert tools["fs"]["workspaceOnly"] is False
    assert config["agents"]["list"][0]["sandbox"]["mode"] == "off"
    after_approvals = parse_config(plans[1].after)
    assert after_approvals["socket"]["token"] == "fixture-socket"
    assert after_approvals["agents"]["main"]["allowlist"] == [{"pattern": "pwd"}]
    for record in (after_approvals["defaults"], *after_approvals["agents"].values()):
        assert {k: record[k] for k in ("security", "ask", "askFallback")} == {
            "security": "full", "ask": "off", "askFallback": "full"}
    public = json.dumps([p.public() for p in plans])
    assert "fixture-secret" not in public and "fixture-socket" not in public
    store = OpenClawStore(tmp_path / "state")
    applied = store.apply(plans)
    assert applied["status"] == "applied"
    store.validate(applied["receipt_id"], home)
    assert store.apply(make_plans(home))["status"] == "unchanged"
    assert all(p.before == p.after for p in make_plans(home))
    assert store.rollback(applied["receipt_id"])["status"] == "rolled_back"
    assert (home / "openclaw.json").read_bytes() == original
    assert (home / "exec-approvals.json").read_bytes() == approvals
    assert store.rollback(applied["receipt_id"])["status"] == "already_rolled_back"


def test_absent_files_restored_as_absent(tmp_path):
    home = tmp_path / "missing"
    store = OpenClawStore(tmp_path / "state")
    result = store.apply(make_plans(home))
    assert (home / "openclaw.json").exists()
    assert (home / "exec-approvals.json").exists()
    store.rollback(result["receipt_id"])
    assert not (home / "openclaw.json").exists()
    assert not (home / "exec-approvals.json").exists()


@pytest.mark.parametrize("source", [
    b'{password:"fixture-secret",password:"other"}', b'{secret:NaN}',
    b'{secret:Infinity}', b'{secret:1e999}', b'{secret: "fixture-secret"',
    b'[]', b'null', b'\xff',
])
def test_invalid_json5_errors_are_redacted(source):
    with pytest.raises(ValueError) as caught:
        parse_config(source)
    assert "fixture-secret" not in str(caught.value)


@pytest.mark.parametrize("source,reason", [
    ('{$include:"extra.json"}', "include"),
    ('{channels:{nested:[{$include:"extra.json"}]}}', "include"),
    ('{gateway:{mode:"remote"}}', "remote"),
    ('{tools:{exec:{host:"node"}}}', "node"),
    ('{agents:{list:[{id:"x",tools:{exec:{host:"node"}}}]}}', "node"),
    ('{tools:{byProvider:{x:{deny:["exec"]}}}}', "byProvider"),
    ('{agents:{list:[{id:"x",tools:{byProvider:{x:{profile:"minimal"}}}}]}}', "byProvider"),
    ('{agents:{list:{x:{}}}}', "agent"),
    ('{agents:{list:["bad"]}}', "agent"),
    ('{agents:{list:[{}]}}', "agent"),
    ('{agents:{list:[{id:"x"},{id:"x"}]}}', "agent"),
])
def test_conflicts_reject_without_writes(home, source, reason):
    target = home / "openclaw.json"
    target.write_text(source)
    with pytest.raises(ValueError, match=reason):
        make_plans(home)
    assert target.read_text() == source
    assert not (home / "exec-approvals.json").exists()


@pytest.mark.parametrize("source", ['{"version":true}', '{"version":2}', '{"version":1,"agents":[]}', '{"version":1,"agents":{"x":null}}'])
def test_approvals_shape_strict(home, source):
    (home / "exec-approvals.json").write_text(source)
    with pytest.raises(ValueError):
        make_plans(home)


def test_stale_second_plan_blocks_first_write(home, tmp_path):
    plans = make_plans(home)
    original = plans[0].before
    (home / "exec-approvals.json").write_text('{"version":1}')
    with pytest.raises(ValueError, match="changed"):
        OpenClawStore(tmp_path / "state").apply(plans)
    assert (home / "openclaw.json").read_bytes() == original


def test_second_apply_failure_compensates_and_keeps_receipt(home, tmp_path, monkeypatch):
    original = (home / "openclaw.json").read_bytes()
    real = Store.apply

    def fail_second(self, plan):
        if plan.target.name == "exec-approvals.json":
            raise OSError("injected failure")
        return real(self, plan)

    monkeypatch.setattr(Store, "apply", fail_second)
    store = OpenClawStore(tmp_path / "state")
    with pytest.raises(ValueError, match="receipt"):
        store.apply(make_plans(home))
    assert (home / "openclaw.json").read_bytes() == original
    assert not (home / "exec-approvals.json").exists()
    _, record = bundle(store)
    store.rollback(record["id"])


def test_orphan_prepared_child_discovered_after_crash(home, tmp_path, monkeypatch):
    original = (home / "openclaw.json").read_bytes()
    real = Store._save

    def crash_after_write(self, record):
        if record["status"] == "applied":
            raise KeyboardInterrupt("simulated interruption")
        return real(self, record)

    monkeypatch.setattr(Store, "_save", crash_after_write)
    store = OpenClawStore(tmp_path / "state")
    with pytest.raises(KeyboardInterrupt):
        store.apply(make_plans(home))
    assert (home / "openclaw.json").read_bytes() != original
    _, record = bundle(store)
    assert record["status"] == "prepared"
    monkeypatch.setattr(Store, "_save", real)
    store.rollback(record["id"])
    assert (home / "openclaw.json").read_bytes() == original
    assert not (home / "exec-approvals.json").exists()


@pytest.mark.parametrize("filename", ["openclaw.json", "exec-approvals.json"])
def test_drift_either_file_blocks_both_restores(home, tmp_path, filename):
    store = OpenClawStore(tmp_path / "state")
    result = store.apply(make_plans(home))
    (home / filename).write_text('{"drift":true}')
    before = {p.name: p.read_bytes() for p in home.iterdir()}
    with pytest.raises(ValueError, match="drift"):
        store.rollback(result["receipt_id"])
    assert {p.name: p.read_bytes() for p in home.iterdir()} == before
    with pytest.raises(ValueError):
        store.validate(result["receipt_id"], home)


def test_all_backups_checked_before_any_restore(home, tmp_path):
    (home / "exec-approvals.json").write_text('{"version":1}')
    store = OpenClawStore(tmp_path / "state")
    result = store.apply(make_plans(home))
    _, record = bundle(store)
    child = record["files"][0]["receipt_id"]
    (store.root / f'{record["id"]}.files' / f"{child}.before").write_bytes(b"corrupt")
    before = {p.name: p.read_bytes() for p in home.iterdir()}
    with pytest.raises(ValueError, match="[Bb]ackup"):
        store.rollback(result["receipt_id"])
    assert {p.name: p.read_bytes() for p in home.iterdir()} == before


@pytest.mark.parametrize("layer", ["child", "bundle"])
def test_rollback_final_save_interruption_is_retryable(home, tmp_path, monkeypatch, layer):
    original = (home / "openclaw.json").read_bytes()
    store = OpenClawStore(tmp_path / "state")
    result = store.apply(make_plans(home))
    cls = Store if layer == "child" else OpenClawStore
    real = cls._save

    def crash(self, record):
        if record["status"] == "rolled_back":
            raise KeyboardInterrupt("simulated interruption")
        return real(self, record)

    monkeypatch.setattr(cls, "_save", crash)
    with pytest.raises(KeyboardInterrupt):
        store.rollback(result["receipt_id"])
    monkeypatch.setattr(cls, "_save", real)
    store.rollback(result["receipt_id"])
    assert (home / "openclaw.json").read_bytes() == original
    assert not (home / "exec-approvals.json").exists()


@pytest.mark.parametrize("field,value", [
    ("id", "../bad"), ("schema", True), ("home", "/tmp/../escape"),
    ("status", []), ("files", []),
])
def test_invalid_manifest_rejected(home, tmp_path, field, value):
    store = OpenClawStore(tmp_path / "state")
    result = store.apply(make_plans(home))
    path, record = bundle(store)
    record[field] = value
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError):
        store.rollback(result["receipt_id"])


@pytest.mark.parametrize("receipt_id", ["../escape", "a" * 31, 5, None])
def test_invalid_ids(tmp_path, receipt_id):
    with pytest.raises(ValueError):
        OpenClawStore(tmp_path / "state").rollback(receipt_id)


def test_validate_checks_exact_home(home, tmp_path):
    store = OpenClawStore(tmp_path / "state")
    result = store.apply(make_plans(home))
    with pytest.raises(ValueError):
        store.validate(result["receipt_id"], tmp_path / "other")
    assert Path(result["receipt"]).name == result["receipt_id"] + ".bundle.json"


@pytest.mark.parametrize("point", ["first_child", "final_bundle"])
def test_bundle_apply_journal_crashes_recover(home, tmp_path, monkeypatch, point):
    original = (home / "openclaw.json").read_bytes()
    store = OpenClawStore(tmp_path / "state")
    real = OpenClawStore._save

    def crash(self, record):
        if ((point == "first_child" and record["files"][0]["receipt_id"] is not None)
                or (point == "final_bundle" and record["status"] == "applied")):
            raise KeyboardInterrupt("simulated interruption")
        return real(self, record)

    monkeypatch.setattr(OpenClawStore, "_save", crash)
    with pytest.raises(KeyboardInterrupt):
        store.apply(make_plans(home))
    _, record = bundle(store)
    monkeypatch.setattr(OpenClawStore, "_save", real)
    store.rollback(record["id"])
    assert (home / "openclaw.json").read_bytes() == original
    assert not (home / "exec-approvals.json").exists()


def test_second_child_write_then_save_error_compensates_both(home, tmp_path, monkeypatch):
    original = (home / "openclaw.json").read_bytes()
    real = Store._save

    def fail(self, record):
        if record["target"].endswith("exec-approvals.json") and record["status"] == "applied":
            raise OSError("save failure")
        return real(self, record)

    monkeypatch.setattr(Store, "_save", fail)
    store = OpenClawStore(tmp_path / "state")
    with pytest.raises(ValueError, match="original files restored"):
        store.apply(make_plans(home))
    assert (home / "openclaw.json").read_bytes() == original
    assert not (home / "exec-approvals.json").exists()
    _, record = bundle(store)
    assert record["status"] == "rolled_back"


def test_failed_compensation_retains_recoverable_bundle(home, tmp_path, monkeypatch):
    original = (home / "openclaw.json").read_bytes()
    real_apply = Store.apply
    real_rollback = Store.rollback

    def fail_second(self, plan):
        if plan.target.name == "exec-approvals.json":
            raise OSError("apply failure")
        return real_apply(self, plan)

    def fail_restore(self, receipt_id):
        raise OSError("restore failure")

    monkeypatch.setattr(Store, "apply", fail_second)
    monkeypatch.setattr(Store, "rollback", fail_restore)
    store = OpenClawStore(tmp_path / "state")
    with pytest.raises(ValueError, match="recovery pending"):
        store.apply(make_plans(home))
    _, record = bundle(store)
    assert record["status"] == "rolling_back"
    assert (home / "openclaw.json").read_bytes() != original
    monkeypatch.setattr(Store, "rollback", real_rollback)
    store.rollback(record["id"])
    assert (home / "openclaw.json").read_bytes() == original


@pytest.mark.parametrize("field,value", [
    ("receipt_id", "../escape"), ("receipt_id", {}), ("before_sha256", True),
    ("after_sha256", "a" * 63), ("target", "/tmp/escape"), ("name", "../openclaw.json"),
])
def test_invalid_file_records_block_all_writes(home, tmp_path, field, value):
    store = OpenClawStore(tmp_path / "state")
    result = store.apply(make_plans(home))
    path, record = bundle(store)
    record["files"][0][field] = value
    path.write_text(json.dumps(record))
    before = {p.name: p.read_bytes() for p in home.iterdir()}
    with pytest.raises(ValueError):
        store.rollback(result["receipt_id"])
    assert {p.name: p.read_bytes() for p in home.iterdir()} == before


@pytest.mark.parametrize("field,value", [
    ("id", "../escape"), ("before_mode", True), ("schema", True),
    ("target", "/tmp/escape"), ("status", []), ("status", "rolled_back"),
])
def test_invalid_child_receipts_block_all_restores(home, tmp_path, field, value):
    store = OpenClawStore(tmp_path / "state")
    result = store.apply(make_plans(home))
    _, record = bundle(store)
    child_id = record["files"][0]["receipt_id"]
    child_path = store.root / f'{record["id"]}.files' / f"{child_id}.json"
    child_record = json.loads(child_path.read_bytes())
    child_record[field] = value
    child_path.write_text(json.dumps(child_record))
    before = {p.name: p.read_bytes() for p in home.iterdir()}
    with pytest.raises(ValueError):
        store.rollback(result["receipt_id"])
    assert {p.name: p.read_bytes() for p in home.iterdir()} == before


def test_unchanged_native_config_has_no_child_receipt(home, tmp_path):
    config_plan = make_plans(home)[0]
    original = b"// preserve this ON comment\n" + config_plan.after
    (home / "openclaw.json").write_bytes(original)
    store = OpenClawStore(tmp_path / "state")
    result = store.apply(make_plans(home))
    _, record = bundle(store)
    assert record["files"][0]["receipt_id"] is None
    store.validate(result["receipt_id"], home)
    store.rollback(result["receipt_id"])
    assert (home / "openclaw.json").read_bytes() == original
    assert not (home / "exec-approvals.json").exists()
