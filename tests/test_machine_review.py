"""Review regressions: owned transport cancellation and structured CLI errors.

Desktop fixtures never launch a native driver or perform UI actions.
"""
import asyncio
import json
import sys
from contextlib import asynccontextmanager
from types import SimpleNamespace

import mcp
import mcp.client.stdio
import pytest

from ballz2thewall import admin, cli, machine
from ballz2thewall.onboarding import Activation


@pytest.fixture
def active(tmp_path):
    state = tmp_path / 'state'
    record = {'schema': 1, 'id': 'a' * 32, 'phase': 'on', 'adapter': 'hermes',
              'home': str(tmp_path), 'after_sha256': 'b' * 64, 'receipt_id': 'c' * 32,
              'machine_access': True}
    Activation(state)._save(record)
    return state, record


@pytest.fixture
def driver(monkeypatch):
    probe = SimpleNamespace(block=None, entered=None, closed=False, cancelled=False,
                            completed=False, params=None, failure=None, calls=[])

    async def stage(name):
        if probe.block == name:
            probe.entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                probe.cancelled = True
                raise
        if probe.failure == name:
            raise ValueError('Fixture driver failure')
        return SimpleNamespace(model_dump=lambda **kwargs: {'stage': name})

    @asynccontextmanager
    async def transport(params):
        probe.params = params
        try:
            await stage('connect')
            yield (None, None)
        finally:
            probe.closed = True

    class Session:
        def __init__(self, *args):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def initialize(self):
            await stage('initialize')

        async def list_tools(self):
            return await stage('list')

        async def call_tool(self, name, arguments):
            probe.calls.append((name, arguments))
            result = await stage('call')
            probe.completed = True
            return result

    monkeypatch.setattr(machine, 'desktop_spec', lambda: {'command': 'fixture-driver', 'args': []})
    monkeypatch.setattr(mcp.client.stdio, 'stdio_client', transport)
    monkeypatch.setattr(mcp, 'ClientSession', Session)
    return probe


@pytest.mark.parametrize('stage', ['connect', 'initialize', 'list', 'call'])
@pytest.mark.parametrize('changes', [{'phase': 'off'}, {'id': 'd' * 32}])
def test_direct_driver_revokes_inflight_at_every_stage(active, driver, stage, changes):
    state, record = active

    async def probe():
        driver.block = stage
        driver.entered = asyncio.Event()
        task = asyncio.create_task(machine.driver_call(
            state, record['id'], None if stage == 'list' else 'desktop_click', {}))
        try:
            await asyncio.wait_for(driver.entered.wait(), timeout=2)
            record.update(changes)
            Activation(state)._save(record)
            # asyncio.wait does not cancel the subject on timeout: failures prove
            # lack of OFF revocation, not the test's own timeout cancellation.
            done, _ = await asyncio.wait({task}, timeout=1.5)
            assert task in done, 'direct desktop operation remained in flight after revocation'
            with pytest.raises(ValueError, match='OFF|activation'):
                await task
            assert driver.closed
            assert driver.cancelled
            assert not driver.completed
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(probe())


def test_direct_driver_preserves_spec_environment(active, driver, monkeypatch):
    state, record = active
    env = {'CUA_DRIVER_PERMISSION_MODE': 'unrestricted',
           'CUA_DRIVER_DANGEROUSLY_BYPASS_APPROVALS': '1', 'DISPLAY': ':fixture'}
    monkeypatch.setattr(machine, 'desktop_spec', lambda: {'command': 'fixture-driver', 'env': env})
    result = asyncio.run(machine.driver_call(state, record['id'], 'desktop_get_config', {}))
    assert result == {'stage': 'call'}
    assert driver.params.env == env
    assert driver.calls == [('get_config', {})]
    assert driver.closed and driver.completed


@pytest.mark.parametrize('tool', [None, 'desktop_get_config'])
def test_direct_driver_success_and_error_cleanup(active, driver, tool):
    state, record = active
    assert asyncio.run(machine.driver_call(state, record['id'], tool, {})) == {
        'stage': 'list' if tool is None else 'call'}
    assert driver.closed
    driver.closed = False
    driver.failure = 'initialize'
    with pytest.raises(ValueError, match='Fixture driver failure'):
        asyncio.run(machine.driver_call(state, record['id'], tool, {}))
    assert driver.closed


def test_direct_driver_caller_cancellation_closes_transport(active, driver):
    state, record = active

    async def probe():
        driver.block = 'call'
        driver.entered = asyncio.Event()
        task = asyncio.create_task(machine.driver_call(state, record['id'], 'desktop_click', {}))
        try:
            await asyncio.wait_for(driver.entered.wait(), timeout=2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert driver.closed and driver.cancelled
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(probe())


@pytest.mark.parametrize('timeout', [0, 120, 601])
def test_cli_admin_off_is_json_error_not_traceback(active, tmp_path, capsys, timeout):
    state, _ = active
    args = {'argv': [sys.executable, '-I', '-c', 'print("unused")'], 'cwd': str(tmp_path),
            'administrator': True, 'timeout': timeout}
    result = cli.main(['machine', 'tool', '--state-dir', str(state), '--tool', 'machine_exec',
                       '--arguments', json.dumps(args)])
    assert result == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {'status': 'error', 'error': 'Administrative helper is off'}
    assert captured.err == ''


@pytest.mark.parametrize('message', ['Administrative helper busy', 'Administrative helper unavailable'])
def test_cli_admin_errors_stay_controlled(active, tmp_path, capsys, monkeypatch, message):
    state, _ = active

    def fail(*args, **kwargs):
        raise admin.AdminError(message)

    monkeypatch.setattr(admin, 'execute', fail)
    args = {'argv': [sys.executable], 'cwd': str(tmp_path), 'administrator': True}
    assert cli.main(['machine', 'tool', '--state-dir', str(state), '--tool', 'machine_exec',
                     '--arguments', json.dumps(args)]) == 2
    assert json.loads(capsys.readouterr().out) == {'status': 'error', 'error': message}


def test_direct_driver_real_stdio_off_closes_owned_transport(active, monkeypatch, tmp_path):
    import mcp.client.stdio
    state, record = active
    started = tmp_path / 'call-started'
    completed = tmp_path / 'action-completed'
    server = tmp_path / 'fixture_server.py'
    server.write_text(
        'import asyncio, pathlib, sys\n'
        'from mcp.server.fastmcp import FastMCP\n'
        'app = FastMCP("scratch-review")\n'
        '@app.tool()\n'
        'async def blocked() -> str:\n'
        '    pathlib.Path(sys.argv[1]).touch()\n'
        '    await asyncio.sleep(30)\n'
        '    pathlib.Path(sys.argv[2]).touch()\n'
        '    return "completed"\n'
        'app.run(transport="stdio")\n', encoding='utf-8')
    monkeypatch.setattr(machine, 'desktop_spec', lambda: {
        'command': sys.executable, 'args': ['-I', str(server), str(started), str(completed)]})
    original = mcp.client.stdio.stdio_client
    closed = []

    @asynccontextmanager
    async def observed(spec):
        try:
            async with original(spec) as streams:
                yield streams
        finally:
            closed.append(True)

    monkeypatch.setattr(mcp.client.stdio, 'stdio_client', observed)

    async def probe():
        task = asyncio.create_task(machine.driver_call(state, record['id'], 'desktop_blocked', {}))
        try:
            deadline = asyncio.get_running_loop().time() + 8
            while not started.exists() and asyncio.get_running_loop().time() < deadline:
                if task.done():
                    await task
                    pytest.fail('direct call finished before entering fixture')
                await asyncio.sleep(0.02)
            assert started.exists()
            record['phase'] = 'off'
            Activation(state)._save(record)
            with pytest.raises(ValueError, match='OFF|revoked'):
                await asyncio.wait_for(task, 8)
            assert not completed.exists()
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    asyncio.run(probe())
    assert closed == [True]
