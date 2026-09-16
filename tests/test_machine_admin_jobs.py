"""Public machine API + actual stdio, injected helper privilege detection only."""
import asyncio
import os
import signal
import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from test_admin import activation
from test_admin import helper as helper
from test_admin import tracked_children as tracked_children
from test_admin_jobs import wait_for

from ballz2thewall import admin, machine, wire_json
from ballz2thewall.machine_jobs import CommandJobs


@pytest.fixture
def jobs(helper):
    manager = CommandJobs(helper, 'a'*32)
    try:
        yield manager
    finally:
        manager.close()


def start(state, jobs, code='print("admin job")', **extra):
    return machine.call_local(state, 'a'*32, 'machine_exec', {
        'argv': [sys.executable, '-I', '-u', '-c', code], 'cwd': str(state),
        'administrator': True, 'background': True, **extra}, jobs=jobs)


def final(jobs, identity):
    return wait_for(lambda: (r if (r := jobs.control('status', identity))['status']
                            not in ('running', 'cancelling') else None))


def test_public_admin_background_completion_and_session_ownership(helper, jobs):
    item = start(helper, jobs)
    assert item['administrator'] is True and item['elevated'] is True and item['timeout'] == 0
    result = final(jobs, item['job_id'])
    assert result['status'] == 'completed' and result['returncode'] == 0
    assert result['elevated'] is True and result['stdout'].strip() == 'admin job'
    other = CommandJobs(helper, 'a'*32)
    try:
        with pytest.raises(ValueError, match='Unknown'):
            other.control('cancel', item['job_id'])
    finally:
        other.close()


def test_helper_off_and_no_session_never_claim_elevated(helper, jobs, tracked_children):
    with pytest.raises(ValueError, match='MCP session'):
        start(helper, None)
    admin.stop(helper)
    with pytest.raises(admin.AdminError, match='off'):
        start(helper, jobs)
    assert jobs.control('list')['jobs'] == [] and tracked_children == []


@pytest.mark.parametrize('mode', ['cancel', 'close', 'off', 'rotate', 'helper-stop'])
def test_public_jobs_cancel_reap_and_reuse(helper, jobs, tracked_children, mode):
    item = start(helper, jobs, 'import time; print("ready",flush=True); time.sleep(30)', timeout=10**4300)
    wait_for(lambda: 'ready' in jobs.control('status', item['job_id'])['stdout'])
    if mode == 'cancel':
        jobs.control('cancel', item['job_id'])
        assert final(jobs, item['job_id'])['status'] == 'cancelled'
        assert final(jobs, start(helper, jobs)['job_id'])['status'] == 'completed'
    elif mode == 'helper-stop':
        admin.stop(helper)
        result = final(jobs, item['job_id'])
        assert result['status'] == 'cancelled' and result['returncode'] != 0
    else:
        if mode != 'close':
            activation(helper, **({'phase': 'off'} if mode == 'off' else {'id': 'd'*32}))
        jobs.close()
        assert jobs._jobs[item['job_id']].result['cancelled']
    assert tracked_children and all(p.poll() is not None for p in tracked_children)


def test_admin_spawn_error_is_failed_not_elevated_success(helper, jobs):
    item = machine.call_local(helper, 'a'*32, 'machine_exec', {
        'argv': [str(helper/'missing-private-command')], 'cwd': str(helper),
        'background': True, 'administrator': True}, jobs=jobs)
    result = final(jobs, item['job_id'])
    assert result['status'] == 'failed' and result['elevated'] is False and result['error']
    assert 'missing-private-command' not in result['error']
    assert jobs.control('list')['jobs'][0]['elevated'] is False


@pytest.mark.parametrize('mode', ['complete', 'cancel', 'disconnect', 'dead-transport'])
def test_real_stdio_admin_jobs_lifecycle(helper, tracked_children, mode):
    before = sys.get_int_max_str_digits()
    async def probe():
        spec = machine.server_spec(helper, 'a'*32)
        spec['args'].append('--no-desktop')
        pid_file = helper / 'scratch-stdio-server.pid'
        if mode == 'dead-transport':
            # Windows asyncio does not launch via the tracked subprocess.Popen.
            # Record the actual server PID, not a Windows venv launcher PID.
            bootstrap = (
                'import os, pathlib, runpy, sys; '
                f'pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid())); '
                'sys.argv[0] = "ballz2thewall"; '
                'runpy.run_module("ballz2thewall", run_name="__main__")'
            )
            index = spec['args'].index('-m')
            assert spec['args'][index + 1] == 'ballz2thewall'
            spec['args'] = spec['args'][:index] + ['-c', bootstrap] + spec['args'][index + 2:]
        async with stdio_client(StdioServerParameters(**spec)) as transport:
            async with ClientSession(*transport) as session:
                await session.initialize()
                code = 'import time; print("MCP_ADMIN",flush=True)'
                if mode != 'complete':
                    code += '; time.sleep(30)'
                response = await asyncio.wait_for(session.call_tool('machine_exec', {
                    'argv': [sys.executable, '-I', '-u', '-c', code], 'cwd': str(helper),
                    'administrator': True, 'background': True, 'timeout': 10**400}), 2)
                assert not response.isError
                item = wire_json.loads(response.content[0].text)
                for _ in range(150):
                    response = await session.call_tool('machine_job', {'operation': 'status', 'job_id': item['job_id']})
                    value = wire_json.loads(response.content[0].text)
                    if 'MCP_ADMIN' in value['stdout']:
                        break
                    await asyncio.sleep(.02)
                assert 'MCP_ADMIN' in value['stdout']
                if mode in ('complete', 'cancel'):
                    if mode == 'cancel':
                        await session.call_tool('machine_job', {'operation': 'cancel', 'job_id': item['job_id']})
                    for _ in range(150):
                        response = await session.call_tool('machine_job', {'operation': 'status', 'job_id': item['job_id']})
                        value = wire_json.loads(response.content[0].text)
                        if value['status'] not in ('running', 'cancelling'):
                            break
                        await asyncio.sleep(.02)
                    assert value['status'] == ('completed' if mode == 'complete' else 'cancelled')
                    assert response.isError == (mode == 'cancel')
                elif mode == 'dead-transport':
                    # Kill only the scratch stdio server, proving helper sees EOF.
                    server_pid = int(pid_file.read_text())
                    assert server_pid > 0 and server_pid != os.getpid()
                    os.kill(server_pid, signal.SIGTERM)
        return True
    asyncio.run(asyncio.wait_for(probe(), 15))
    wait_for(lambda: tracked_children and all(p.poll() is not None for p in tracked_children))
    assert sys.get_int_max_str_digits() == before


def test_huge_result_serialization_keeps_exact_timeout(helper, jobs):
    before = sys.get_int_max_str_digits()
    timeout = 10**4300
    item = start(helper, jobs, timeout=timeout)
    result = final(jobs, item['job_id'])
    assert wire_json.loads(wire_json.dumps(result))['timeout'] == timeout
    assert wire_json.loads(wire_json.dumps(jobs.control('list')))['jobs'][0]['timeout'] == timeout
    assert sys.get_int_max_str_digits() == before


def test_local_thread_start_failure_closes_remote_owner(helper, jobs, tracked_children, monkeypatch):
    from types import SimpleNamespace

    import ballz2thewall.machine_jobs as module
    class FailedThread:
        def __init__(self, *args, **kwargs):
            pass
        def start(self):
            raise RuntimeError('injected local thread start failure')
    monkeypatch.setattr(module, 'threading', SimpleNamespace(Thread=FailedThread))
    with pytest.raises(RuntimeError, match='injected local'):
        start(helper, jobs, 'import time; time.sleep(30)')
    assert jobs.control('list')['jobs'] == []
    wait_for(lambda: all(p.poll() is not None for p in tracked_children))
    assert admin.status(helper)['status'] == 'ready'


def test_thread_constructor_failure_closes_remote_owner(helper, jobs, tracked_children, monkeypatch):
    from types import SimpleNamespace

    import ballz2thewall.machine_jobs as module
    from ballz2thewall.admin_jobs import RemoteCommand

    remotes = []
    original = RemoteCommand.__init__

    def capture(self, *args, **kwargs):
        original(self, *args, **kwargs)
        remotes.append(self)
        # Acceptance precedes asynchronous spawn. Force an actual live child
        # before injecting failure, rather than racing safe pre-spawn cancel.
        wait_for(lambda: tracked_children and any(p.poll() is None for p in tracked_children))

    def broken_constructor(*args, **kwargs):
        raise RuntimeError('injected thread constructor failure')

    monkeypatch.setattr(RemoteCommand, '__init__', capture)
    monkeypatch.setattr(module, 'threading', SimpleNamespace(Thread=broken_constructor))
    try:
        # Keep the exception/traceback alive, as real error reporting does.
        with pytest.raises(RuntimeError, match='thread constructor') as caught:
            start(helper, jobs, 'import time; print("ready",flush=True); time.sleep(30)')
        assert caught.value.__traceback__ is not None
        assert len(remotes) == 1
        assert remotes[0].connection is None
        wait_for(lambda: tracked_children and all(p.poll() is not None for p in tracked_children))
        assert jobs.control('list')['jobs'] == []
    finally:
        for remote in remotes:
            remote.close()
        wait_for(lambda: tracked_children and all(p.poll() is not None for p in tracked_children))


def test_tools_describe_supported_admin_background():
    tool = next(t for t in machine.local_tools() if t.name == 'machine_exec')
    assert 'foreground only' not in tool.description
    assert 'owner approval' in tool.description
