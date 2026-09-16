"""Pure MCP merge tests. Native parsers exercised separately in scratch homes."""
import json

import pytest
import tomlkit
import yaml

from ballz2thewall.adapters import get_adapter
from ballz2thewall.config import Plan, make_plan
from ballz2thewall.machine_bindings import SERVER_NAME, augment_plan, claude_config


@pytest.mark.parametrize('adapter,filename,content,invalid', [
    ('hermes', 'config.yaml', 'mcp_servers: []\n', True),
    ('codex', 'config.toml', 'mcp_servers = []\n', True),
    ('hermes', 'config.yaml', 'mcp_servers:\n  other:\n    command: keep\n', False),
    ('codex', 'config.toml', '[mcp_servers.other]\ncommand = "keep"\n', False),
])
def test_merge_preserves_other_servers_or_rejects_type(tmp_path, adapter, filename, content, invalid):
    path = tmp_path / filename
    path.write_bytes(content.encode())
    plan = make_plan(get_adapter(adapter), tmp_path)
    if invalid:
        with pytest.raises(ValueError, match='MCP section'):
            augment_plan(plan, tmp_path / 'state', 'a' * 32)
    else:
        result = augment_plan(plan, tmp_path / 'state', 'a' * 32)
        document = (yaml.safe_load if adapter == 'hermes' else tomlkit.parse)(result.after.decode())
        assert document['mcp_servers']['other']['command'] == 'keep'
        assert document['mcp_servers'][SERVER_NAME]['enabled'] is True
        assert result.before == content.encode()
        assert f'mcp_servers.{SERVER_NAME}' in result.changes
    assert path.read_text() == content  # planning never writes


@pytest.mark.parametrize('name', ['hermes', 'codex'])
def test_existing_owned_key_is_not_overwritten(tmp_path, name):
    if name == 'hermes':
        (tmp_path / 'config.yaml').write_text(f'mcp_servers:\n  {SERVER_NAME}: {{command: keep}}\n')
    else:
        (tmp_path / 'config.toml').write_text(f'[mcp_servers.{SERVER_NAME}]\ncommand="keep"\n')
    with pytest.raises(ValueError, match='already exists'):
        augment_plan(make_plan(get_adapter(name), tmp_path), tmp_path, 'a' * 32)


def test_claude_only_launch_payload_and_no_model_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv('DISPLAY', ':91')
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-not-a-live-credential')
    payload = claude_config(tmp_path, 'a' * 32)
    server = payload['mcpServers'][SERVER_NAME]
    assert server['type'] == 'stdio'
    assert server['args'][:4] == ['-I', '-m', 'ballz2thewall', 'machine']
    assert server['env']['DISPLAY'] == ':91'
    assert 'OPENAI_API_KEY' not in server['env']
    plan = make_plan(get_adapter('claude'), tmp_path)
    assert augment_plan(plan, tmp_path, 'a' * 32) is plan


@pytest.mark.parametrize('mcp', [[], {'servers': []}, {'servers': {SERVER_NAME: {}}}])
def test_openclaw_invalid_or_collision(tmp_path, mcp):
    data = json.dumps({'mcp': mcp}).encode()
    plan = Plan(tmp_path / 'openclaw.json', b'{}', data, {}, 'openclaw')
    with pytest.raises(ValueError):
        augment_plan(plan, tmp_path, 'a' * 32)
