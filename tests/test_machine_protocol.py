"""Real stdio MCP round trips against installed entrypoint; no OS grants/UI actions."""
import asyncio
import json
import os
import subprocess
import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from ballz2thewall import cli, machine
from ballz2thewall.onboarding import Activation


def test_native_desktop_driver_initializes_and_off_closes(tmp_path):
    from mcp.shared.exceptions import McpError
    state, record = activation(tmp_path)
    spec = machine.server_spec(state, record['id'])
    spec['env'] = {'HOME': str(tmp_path), 'USERPROFILE': str(tmp_path),
                   'XDG_CONFIG_HOME': str(tmp_path/'config'),
                   'XDG_STATE_HOME': str(tmp_path/'data'),
                   'XDG_CACHE_HOME': str(tmp_path/'cache')}

    async def roundtrip():
        async with stdio_client(StdioServerParameters(**spec)) as transport:
            async with ClientSession(*transport) as session:
                await session.initialize()
                names = {tool.name for tool in (await session.list_tools()).tools}
                assert {'machine_exec', 'desktop_get_config', 'desktop_click'} <= names
                config = await session.call_tool('desktop_get_config', {})
                assert not config.isError
                record['phase'] = 'stopping'
                Activation(state)._save(record)
                await asyncio.sleep(1.2)
                with pytest.raises((McpError, ConnectionError)):
                    await asyncio.wait_for(session.list_tools(), timeout=6)
    asyncio.run(asyncio.wait_for(roundtrip(), timeout=40))


def test_native_direct_desktop_cli_discovery_and_config(tmp_path):
    state, _ = activation(tmp_path)
    env = dict(os.environ, HOME=str(tmp_path), USERPROFILE=str(tmp_path),
               XDG_CONFIG_HOME=str(tmp_path/'config'), XDG_STATE_HOME=str(tmp_path/'data'),
               XDG_CACHE_HOME=str(tmp_path/'cache'))
    base = [sys.executable, '-I', '-m', 'ballz2thewall', 'machine']
    result = subprocess.run([*base, 'tools', '--state-dir', str(state)], cwd=tmp_path,
                            env=env, capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stderr
    listing = json.loads(result.stdout)
    assert 'machine_exec' in {tool['name'] for tool in listing['tools']}
    assert 'get_config' in {tool['name'] for tool in listing['desktop']['tools']}
    result = subprocess.run([*base, 'tool', '--state-dir', str(state), '--tool', 'desktop_get_config'],
                            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['isError'] is False


def activation(tmp_path):
    state = tmp_path / 'state'
    record = {'schema': 1, 'id': 'a' * 32, 'phase': 'on', 'adapter': 'hermes',
              'home': str(tmp_path), 'after_sha256': 'b' * 64, 'receipt_id': 'c' * 32,
              'machine_access': True}
    Activation(state)._save(record)
    return state, record


def test_actual_stdio_exec_file_and_off(tmp_path):
    state, record = activation(tmp_path)

    async def probe():
        spec = machine.server_spec(state, record['id'])
        spec['args'].append('--no-desktop')
        async with stdio_client(StdioServerParameters(**spec)) as transport:
            async with ClientSession(*transport) as session:
                await session.initialize()
                names = [t.name for t in (await session.list_tools()).tools]
                assert names == ['machine_status', 'machine_exec', 'machine_file', 'machine_job']
                result = await session.call_tool('machine_exec', {'argv': [sys.executable, '-I', '-c',
                    'print("REAL_STDIO_OK")'], 'cwd': str(tmp_path)})
                assert not result.isError
                assert json.loads(result.content[0].text)['stdout'] == 'REAL_STDIO_OK' + os.linesep
                for timeout in (0, 601):
                    result = await session.call_tool('machine_exec', {
                        'argv': [sys.executable], 'cwd': str(tmp_path),
                        'administrator': True, 'timeout': timeout})
                    payload = result.model_dump(mode='json')
                    assert payload['isError']
                    assert payload['content'][0]['text'] == 'Administrative helper is off'
                target = tmp_path / 'stdio.txt'
                result = await session.call_tool('machine_file', {'operation': 'write', 'path': str(target),
                                                                 'text': 'REAL_STDIO_FILE'})
                assert not result.isError
                assert target.read_text() == 'REAL_STDIO_FILE'
                record['phase'] = 'stopping'
                Activation(state)._save(record)
                # Existing connection must reject the write or be disconnected.
                try:
                    result = await session.call_tool('machine_file', {'operation': 'write',
                        'path': str(tmp_path / 'must-not-exist'), 'text': 'bad'})
                    assert result.isError
                except Exception as exc:
                    from mcp.shared.exceptions import McpError
                    assert isinstance(exc, (McpError, ConnectionError))
                assert not (tmp_path / 'must-not-exist').exists()
    asyncio.run(asyncio.wait_for(probe(), timeout=30))


def test_cli_nonzero_command_is_nonzero_exit(tmp_path, capsys):
    state, _ = activation(tmp_path)
    args = {'argv': [sys.executable, '-I', '-c', 'raise SystemExit(7)'], 'cwd': str(tmp_path)}
    result = cli.main(['machine', 'tool', '--state-dir', str(state), '--tool', 'machine_exec',
                       '--arguments', json.dumps(args)])
    assert result != 0
    assert json.loads(capsys.readouterr().out)['returncode'] == 7


def test_unlimited_command_cancelled_by_off(tmp_path):
    import concurrent.futures
    import time
    state, record = activation(tmp_path)
    started = tmp_path / 'started'
    with concurrent.futures.ThreadPoolExecutor() as pool:
        job = pool.submit(machine.call_local, state, record['id'], 'machine_exec', {
            'argv': [sys.executable, '-I', '-c',
                     'import pathlib,sys,time; pathlib.Path(sys.argv[1]).touch(); time.sleep(60)', str(started)],
            'cwd': str(tmp_path), 'timeout': 0})
        deadline = time.monotonic() + 5
        while not started.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        try:
            assert started.exists()
        finally:
            record['phase'] = 'stopping'
            Activation(state)._save(record)
        result = job.result(timeout=5)
        assert result['cancelled'] is True
        assert result['timed_out'] is False
        assert result['returncode'] != 0


def test_long_positive_timeout_is_allowed(tmp_path):
    result = machine.run_command([sys.executable, '-I', '-c', 'print("long accepted")'],
                                 str(tmp_path), timeout=86400)
    assert result['returncode'] == 0
