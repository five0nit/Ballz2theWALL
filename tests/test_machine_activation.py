"""Machine-access wiring, revocation and launcher contracts; scratch homes only."""
import json
from unittest.mock import Mock

import pytest

from ballz2thewall import cli, machine, onboarding
from ballz2thewall.adapters import ADAPTERS
from ballz2thewall.config import parse


@pytest.fixture
def control(tmp_path, monkeypatch):
    monkeypatch.setattr(onboarding, "require_runtime", lambda *a: {"executable": "fixture"})
    home = tmp_path / "agent"
    home.mkdir()
    return onboarding.Activation(tmp_path / "state"), home


@pytest.mark.parametrize("name", ["hermes", "codex", "claude"])
def test_machine_on_off_real_file_roundtrip(control, name, tmp_path):
    ctl, home = control
    target = home / ADAPTERS[name].filename
    original = {'hermes': b'# exact original\nkeep: 42\n',
                'codex': b'# exact original\n', 'claude': b'{"keep":42}\n'}[name]
    target.write_bytes(original)
    record = ctl.enable(name, home, machine_access=True)
    assert machine.require_on(ctl.root.parent, record['id'])['machine_access'] is True
    assert ctl.enable(name, home, machine_access=True)['id'] == record['id']
    data = parse(target.read_bytes(), target.name)
    if name != 'claude':
        assert data['mcp_servers']['ballz2thewall_machine']['command']
    out = machine.call_local(ctl.root.parent, record['id'], 'machine_file', {
        'operation': 'write', 'path': str(tmp_path / 'real.txt'), 'text': 'WIRED_MACHINE_OK'})
    assert out['bytes'] == len('WIRED_MACHINE_OK')
    ctl.disable()
    assert target.read_bytes() == original
    with pytest.raises(ValueError, match='OFF'):
        machine.require_on(ctl.root.parent, record['id'])


def test_legacy_on_requires_explicit_off_before_upgrade(control):
    ctl, home = control
    ctl.enable('hermes', home)
    with pytest.raises(ValueError, match='OFF'):
        ctl.enable('hermes', home, machine_access=True)


def test_drift_still_revokes_machine_calls(control, monkeypatch):
    ctl, home = control
    record = ctl.enable('hermes', home, machine_access=True)
    stopped = []
    monkeypatch.setattr('ballz2thewall.admin.disable', lambda state: stopped.append(state))
    (home / 'config.yaml').write_text('newer: edit\n')
    with pytest.raises(ValueError, match='drift'):
        ctl.disable()
    assert stopped == [ctl.root.parent]
    with pytest.raises(ValueError, match='OFF'):
        machine.require_on(ctl.root.parent, record['id'])


def test_on_cli_chooses_machine_access(control, capsys):
    ctl, home = control
    assert cli.main(['on', 'hermes', '--home', str(home), '--state-dir', str(ctl.root.parent)]) == 0
    assert json.loads(capsys.readouterr().out)['machine_access'] is True
    ctl.disable()


def test_claude_managed_launch_has_mcp(control, capsys):
    ctl, home = control
    ctl.enable('claude', home, machine_access=True)
    argv = ['run', 'claude', '--home', str(home), '--cwd', str(home), '--state-dir', str(ctl.root.parent),
            '--prompt', 'test', '--dry-run']
    assert cli.main(argv) == 0
    data = json.loads(capsys.readouterr().out)
    i = data['argv'].index('--mcp-config')
    assert 'ballz2thewall_machine' in json.loads(data['argv'][i+1])['mcpServers']
    ctl.disable()
    assert cli.main(argv) == 0
    assert '--mcp-config' not in json.loads(capsys.readouterr().out)['argv']


def test_launcher_preserves_explicit_state(control, monkeypatch):
    ctl, home = control
    active = ctl.enable('claude', home, machine_access=True)
    monkeypatch.setattr(onboarding.platform, 'system', lambda: 'Linux')
    runner = Mock(return_value=0)
    monkeypatch.setattr(cli, 'main', runner)
    onboarding.launch_interactive(active, ctl.root.parent)
    assert runner.call_args.args[0][-2:] == ['--state-dir', str(ctl.root.parent)]


def test_openclaw_both_files_restore_with_binding(control, monkeypatch):
    from ballz2thewall import openclaw_runtime
    ctl, home = control
    originals = {'openclaw.json': b'{/* original */}\n', 'exec-approvals.json': b'{"version":1}\n'}
    for name, data in originals.items():
        (home / name).write_bytes(data)
    monkeypatch.setattr(openclaw_runtime, 'verify_native', lambda *a: {'native_valid': True})
    record = ctl.enable('openclaw', home, machine_access=True)
    config = json.loads((home / 'openclaw.json').read_text())
    assert config['mcp']['servers']['ballz2thewall_machine']['enabled'] is True
    assert machine.require_on(ctl.root.parent, record['id'])
    assert ctl.enable('openclaw', home, machine_access=True)['id'] == record['id']
    ctl.disable()
    assert {name: (home / name).read_bytes() for name in originals} == originals


@pytest.mark.parametrize('choice', ['Use account access only', None])
def test_admin_guide_decline_never_elevates(control, monkeypatch, choice):
    from ballz2thewall import admin
    ctl, _ = control
    monkeypatch.setattr(onboarding.platform, 'system', lambda: 'Windows')
    monkeypatch.setattr(admin, 'status', lambda _: {'status': 'off', 'elevated': False})
    enable = Mock()
    monkeypatch.setattr(admin, 'enable', enable)
    dialogs = Mock()
    dialogs.choose.return_value = choice
    onboarding.guide_admin(ctl.root.parent, dialogs)
    enable.assert_not_called()


@pytest.mark.parametrize('ready', [True, False])
def test_admin_guide_checks_actual_ready(control, monkeypatch, ready):
    from ballz2thewall import admin
    ctl, _ = control
    monkeypatch.setattr(onboarding.platform, 'system', lambda: 'Windows')
    monkeypatch.setattr(admin, 'status', lambda _: {'status': 'off', 'elevated': False})
    enable = Mock(return_value={'status': 'ready' if ready else 'unavailable', 'elevated': ready})
    monkeypatch.setattr(admin, 'enable', enable)
    dialogs = Mock()
    dialogs.choose.return_value = 'Approve Administrator access'
    onboarding.guide_admin(ctl.root.parent, dialogs)
    enable.assert_called_once_with(ctl.root.parent)
    assert dialogs.message.called is (not ready)


def test_admin_guide_already_ready_does_not_prompt(control, monkeypatch):
    from ballz2thewall import admin
    ctl, _ = control
    monkeypatch.setattr(onboarding.platform, 'system', lambda: 'Windows')
    monkeypatch.setattr(admin, 'status', lambda _: {'status': 'ready', 'elevated': True})
    dialogs = Mock()
    assert onboarding.guide_admin(ctl.root.parent, dialogs)['elevated']
    dialogs.choose.assert_not_called()


def test_admin_timeout_reopen_explicit_retry_revokes_reservation(control, monkeypatch):
    import subprocess

    from ballz2thewall import admin
    ctl, home = control
    ctl.enable('hermes', home, machine_access=True)
    monkeypatch.setattr(onboarding.platform, 'system', lambda: 'Windows')
    monkeypatch.setattr(admin, 'WINDOWS', True)
    monkeypatch.setattr(admin, '_identity', lambda: 'fixture-sid')
    launch = Mock(side_effect=subprocess.TimeoutExpired('fixture-uac', 120))
    monkeypatch.setattr(admin, '_launch', launch)
    dialogs = Mock()
    dialogs.choose.side_effect = ['Approve Administrator access', 'Cancel pending approval and retry']
    first = onboarding.guide_admin(ctl.root.parent, dialogs)
    assert first['status'] == 'pending' and first['elevated'] is False
    store = admin._store(ctl.root.parent)
    old = admin._read(store.root / 'pending.json')
    assert old is not None
    second = onboarding.guide_admin(ctl.root.parent, dialogs)
    assert second['status'] == 'pending' and launch.call_count == 2
    new = admin._read(store.root / 'pending.json')
    assert new is not None and new['launch_id'] != old['launch_id']
    assert 'launch_id' not in second and 'sid' not in second
    assert 'pending' in dialogs.message.call_args.args[1].lower()
    ctl.disable()


@pytest.mark.parametrize('choice', ['Keep pending approval', None])
def test_admin_pending_decline_preserves_reservation(control, monkeypatch, choice):
    from ballz2thewall import admin
    ctl, _ = control
    monkeypatch.setattr(onboarding.platform, 'system', lambda: 'Windows')
    current = {'status': 'pending', 'elevated': False}
    monkeypatch.setattr(admin, 'status', lambda _: current)
    enable, disable = Mock(), Mock()
    monkeypatch.setattr(admin, 'enable', enable)
    monkeypatch.setattr(admin, 'disable', disable)
    dialogs = Mock()
    dialogs.choose.return_value = choice
    assert onboarding.guide_admin(ctl.root.parent, dialogs) == current
    enable.assert_not_called()
    disable.assert_not_called()


def test_admin_pending_cleanup_failure_prevents_new_approval(control, monkeypatch):
    from ballz2thewall import admin
    ctl, _ = control
    monkeypatch.setattr(onboarding.platform, 'system', lambda: 'Windows')
    monkeypatch.setattr(admin, 'status', lambda _: {'status': 'pending', 'elevated': False})
    disable = Mock(return_value={'status': 'unavailable', 'error': 'fixture cleanup failed'})
    enable = Mock()
    monkeypatch.setattr(admin, 'enable', enable)
    monkeypatch.setattr(admin, 'disable', disable)
    dialogs = Mock()
    dialogs.choose.return_value = 'Cancel pending approval and retry'
    onboarding.guide_admin(ctl.root.parent, dialogs)
    disable.assert_called_once_with(ctl.root.parent)
    enable.assert_not_called()
    assert dialogs.message.called


def test_failed_admin_cleanup_keeps_activation_revoked(control, monkeypatch):
    ctl, home = control
    record = ctl.enable('hermes', home, machine_access=True)
    monkeypatch.setattr('ballz2thewall.admin.disable', lambda _: {'error': 'fixture failure'})
    with pytest.raises(ValueError, match='cleanup failed'):
        ctl.disable()
    assert ctl.status()['phase'] == 'stopping'
    with pytest.raises(ValueError, match='OFF'):
        machine.require_on(ctl.root.parent, record['id'])
    monkeypatch.setattr('ballz2thewall.admin.disable', lambda _: {'status': 'off'})
    assert ctl.disable()['phase'] == 'off'


@pytest.mark.parametrize('action,method', [('admin-on', 'enable'), ('admin-off', 'disable')])
def test_admin_cli_failed_operation_returns_nonzero(control, monkeypatch, capsys, action, method):
    ctl, home = control
    ctl.enable('hermes', home, machine_access=True)
    monkeypatch.setattr('ballz2thewall.admin.' + method,
                        lambda _: {'status': 'unavailable', 'elevated': False, 'error': 'fixture failure'})
    assert cli.main(['machine', action, '--state-dir', str(ctl.root.parent)]) == 2
    assert json.loads(capsys.readouterr().out)['error'] == 'fixture failure'
