"""Isolated consumer-access contract; never changes the desktop or privileges."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from ballz2thewall import machine
from ballz2thewall.onboarding import Activation


@pytest.fixture
def active(tmp_path):
    state = tmp_path / 'state'
    record = {'schema': 1, 'id': 'a' * 32, 'phase': 'on', 'adapter': 'hermes',
              'home': str(tmp_path), 'after_sha256': 'b' * 64, 'receipt_id': 'c' * 32,
              'machine_access': True}
    Activation(state)._save(record)
    return state, record


def test_gate_rejects_off_before_execution(tmp_path, monkeypatch):
    monkeypatch.setattr(machine.subprocess, 'Popen', lambda *a, **k: pytest.fail('executed while OFF'))
    with pytest.raises(ValueError, match='OFF|active'):
        machine.call_local(tmp_path, 'a' * 32, 'machine_exec', {'argv': ['anything'], 'cwd': str(tmp_path)})


def test_gate_rejects_stale_activation(active):
    state, _ = active
    with pytest.raises(ValueError, match='activation'):
        machine.require_on(state, 'd' * 32)


def test_legacy_runtime_on_does_not_grant_machine_access(active):
    state, record = active
    record.pop('machine_access')
    Activation(state)._save(record)
    with pytest.raises(ValueError, match='machine'):
        machine.require_on(state, record['id'])


def test_real_command_roundtrip(active, tmp_path):
    state, record = active
    result = machine.call_local(state, record['id'], 'machine_exec',
        {'argv': [sys.executable, '-I', '-c', 'import os; print(os.getcwd()); print("BALLZ_MACHINE_OK")'], 'cwd': str(tmp_path)})
    assert result['returncode'] == 0
    assert 'BALLZ_MACHINE_OK' in result['stdout']
    assert str(tmp_path) in result['stdout']
    assert result['elevated'] is False


def test_command_nonzero_is_not_success(active, tmp_path):
    state, record = active
    result = machine.call_local(state, record['id'], 'machine_exec',
        {'argv': [sys.executable, '-c', 'import sys; print("err",file=sys.stderr); sys.exit(7)'], 'cwd': str(tmp_path)})
    assert result['returncode'] == 7 and 'err' in result['stderr']


def test_command_timeout_and_output_bound(active, tmp_path):
    state, record = active
    result = machine.call_local(state, record['id'], 'machine_exec',
        {'argv': [sys.executable, '-u', '-c', 'import time; print("x"*300000); time.sleep(5)'],
         'cwd': str(tmp_path), 'timeout': 1})
    assert result['timed_out'] is True
    assert result['truncated'] is True
    assert len(result['stdout'].encode()) <= machine.OUTPUT_LIMIT


@pytest.mark.parametrize('argv', ['echo bad', [], [1], ['ok', '\x00'], ['x' * 70000]])
def test_invalid_argv(active, tmp_path, argv):
    state, record = active
    with pytest.raises(ValueError):
        machine.call_local(state, record['id'], 'machine_exec', {'argv': argv, 'cwd': str(tmp_path)})


@pytest.mark.parametrize('timeout', [-1, False, True, '5'])
def test_invalid_timeout(active, tmp_path, timeout):
    state, record = active
    with pytest.raises(ValueError):
        machine.call_local(state, record['id'], 'machine_exec', {'argv': ['x'], 'cwd': str(tmp_path), 'timeout': timeout})


def test_files_roundtrip_and_explicit_overwrite(active, tmp_path):
    state, record = active
    target = tmp_path / 'hello world.txt'
    args = {'operation': 'write', 'path': str(target), 'text': 'Real tool output.\n'}
    out = machine.call_local(state, record['id'], 'machine_file', args)
    assert out['bytes'] == len(args['text'].encode())
    with pytest.raises(ValueError, match='overwrite'):
        machine.call_local(state, record['id'], 'machine_file', args)
    out = machine.call_local(state, record['id'], 'machine_file', {'operation': 'read', 'path': str(target)})
    assert out['text'] == args['text'] and not out['truncated']
    out = machine.call_local(state, record['id'], 'machine_file', {'operation': 'list', 'path': str(tmp_path)})
    assert target.name in [item['name'] for item in out['entries']]


def test_off_revokes_already_created_client(active, tmp_path):
    state, record = active
    machine.require_on(state, record['id'])
    record['phase'] = 'stopping'
    Activation(state)._save(record)
    with pytest.raises(ValueError):
        machine.call_local(state, record['id'], 'machine_file', {'operation': 'write', 'path': str(tmp_path / 'no'), 'text': 'no'})
    assert not (tmp_path / 'no').exists()


def test_machine_tool_schemas_are_valid():
    from jsonschema import Draft202012Validator
    names = []
    for tool in machine.local_tools():
        Draft202012Validator.check_schema(tool.inputSchema)
        names.append(tool.name)
    assert names == ['machine_status', 'machine_exec', 'machine_file', 'machine_job']


def test_admin_requires_separate_approved_helper(active, tmp_path, monkeypatch):
    state, record = active
    from ballz2thewall import admin
    monkeypatch.setattr(admin, 'execute', lambda *a, **k: (_ for _ in ()).throw(ValueError('Administrator helper is OFF')))
    with pytest.raises(ValueError, match='OFF'):
        machine.call_local(state, record['id'], 'machine_exec', {'argv': ['x'], 'cwd': str(tmp_path), 'administrator': True})


def test_cli_registration_no_shell_or_secret(active):
    state, record = active
    spec = machine.server_spec(state, record['id'])
    assert Path(spec['command']).is_absolute()
    assert spec['args'][:3] == ['-I', '-m', 'ballz2thewall']
    assert '--activation-id' in spec['args']
    assert json.dumps(spec).find('auth_token') == -1
