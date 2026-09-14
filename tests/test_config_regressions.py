"""Config merge edge cases: preserve aliases, replace wrong scalar types."""
from pathlib import Path

import pytest

from ballz2thewall.adapters import get_adapter
from ballz2thewall.config import make_plan, parse


@pytest.mark.parametrize("adapter,filename,data", [
    ("hermes", "config.yaml", b"approvals:\n  mode: 'off'\n  cron_mode: approve\n  single_query_mode: approve\n  unattended_mode: approve\nterminal:\n  backend: local\nsecurity:\n  allow_private_urls: 1\nbrowser:\n  allow_private_urls: true\n"),
    ("claude", "settings.json", b'{"permissions":{"defaultMode":"bypassPermissions"},"sandbox":{"enabled":0}}'),
])
def test_wrong_boolean_type_is_not_a_noop(tmp_path, adapter, filename, data):
    target = tmp_path / filename
    target.write_bytes(data)
    plan = make_plan(get_adapter(adapter), tmp_path)
    assert plan.public()["changed"]
    parsed = parse(plan.after, filename)
    value = parsed["security"]["allow_private_urls"] if adapter == "hermes" else parsed["sandbox"]["enabled"]
    assert isinstance(value, bool)


def test_yaml_alias_does_not_mutate_unrelated_values(tmp_path: Path):
    (tmp_path / "config.yaml").write_text("approvals: &common\n  mode: manual\ncustom: *common\n")
    result = parse(make_plan(get_adapter("hermes"), tmp_path).after, "config.yaml")
    assert result["approvals"]["mode"] == "off"
    assert result["custom"] == {"mode": "manual"}
