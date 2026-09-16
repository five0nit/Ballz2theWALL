"""Session-owned command jobs: real child processes, scratch state, no OS grants."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

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


@pytest.fixture
def jobs(active):
    from ballz2thewall.machine_jobs import CommandJobs
    state, record = active
    manager = CommandJobs(state, record['id'])
    try:
        yield manager
    finally:
        manager.close()


def argv(code):
    return [sys.executable, '-I', '-u', '-c', code]


def wait_for(predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.02)
    pytest.fail('scratch command did not reach expected state')


def finished(jobs, job_id):
    return wait_for(lambda: (r if (r := jobs.control('status', job_id))['status']
                             not in {'running', 'cancelling'} else None))


def test_background_returns_quickly_and_exposes_partial_output(active, jobs, tmp_path):
    state, record = active
    stop = tmp_path / 'finish'
    code = ('import pathlib,sys,time; sys.stdout.write("partial"); sys.stdout.flush(); '
            'sys.stderr.write("progress"); sys.stderr.flush(); '
            f'p=pathlib.Path({str(stop)!r})\n'
            'while not p.exists(): time.sleep(.02)\n'
            'print(" complete")')
    before = time.monotonic()
    first = machine.call_local(state, record['id'], 'machine_exec', {
        'argv': argv(code), 'cwd': str(tmp_path), 'background': True, 'timeout': 0}, jobs=jobs)
    assert time.monotonic() - before < 2
    assert first['status'] == 'running'
    job_id = first['job_id']
    partial = wait_for(lambda: (r if (r := jobs.control('status', job_id))['stdout'] == 'partial'
                               and r['stderr'] == 'progress' else None))
    assert partial['status'] == 'running'
    assert 'returncode' not in partial
    listing = jobs.control('list')
    assert [j['job_id'] for j in listing['jobs']] == [job_id]
    assert 'stdout' not in listing['jobs'][0]
    stop.touch()
    result = finished(jobs, job_id)
    assert result['status'] == 'completed' and result['returncode'] == 0
    assert result['stdout'] == 'partial complete' + os.linesep
    assert not result['timed_out'] and not result['cancelled']


def test_cancel_is_explicit_and_idempotent(jobs, tmp_path):
    started = tmp_path / 'started'
    result = jobs.start(argv(f'import pathlib,time; pathlib.Path({str(started)!r}).touch(); time.sleep(30)'),
                        str(tmp_path), 0)
    wait_for(started.exists)
    assert jobs.control('cancel', result['job_id'])['status'] in {'cancelling', 'cancelled'}
    final = finished(jobs, result['job_id'])
    assert final['cancelled'] and not final['timed_out']
    assert final['returncode'] != 0 and final['status'] == 'cancelled'
    assert jobs.control('cancel', result['job_id']) == final


@pytest.mark.parametrize('code,timeout,status,returncode', [
    ('raise SystemExit(7)', 0, 'failed', 7),
    ('import time; time.sleep(30)', 1, 'timed_out', None),
    ('print("long deadline")', 86400, 'completed', 0),
])
def test_terminal_statuses(jobs, tmp_path, code, timeout, status, returncode):
    result = finished(jobs, jobs.start(argv(code), str(tmp_path), timeout)['job_id'])
    assert result['status'] == status
    if returncode is not None:
        assert result['returncode'] == returncode
    else:
        assert result['timed_out'] and result['returncode'] != 0


def test_output_is_bounded_and_non_utf8_is_readable(jobs, tmp_path):
    result = finished(jobs, jobs.start(argv(
        'import os; os.write(1,b"x"*300000); os.write(2,b"\\xff")'), str(tmp_path), 0)['job_id'])
    assert result['truncated']
    assert len(result['stdout']) == machine.OUTPUT_LIMIT
    assert result['stderr'] == '\ufffd'


def test_spawn_error_is_terminal_without_leaking_arguments(jobs, tmp_path):
    result = finished(jobs, jobs.start([str(tmp_path/'missing-private-name')], str(tmp_path), 0)['job_id'])
    assert result['status'] == 'failed' and result['error']
    assert 'missing-private-name' not in result['error']


@pytest.mark.parametrize('change', [{'phase': 'off'}, {'id': 'd' * 32}, {'machine_access': False}])
def test_revocation_stops_jobs_and_blocks_old_handle(active, jobs, tmp_path, change):
    state, record = active
    started = tmp_path / 'started'
    job_id = jobs.start(argv(f'import pathlib,time; pathlib.Path({str(started)!r}).touch(); time.sleep(30)'),
                        str(tmp_path), 0)['job_id']
    wait_for(started.exists)
    record.update(change)
    Activation(state)._save(record)
    with pytest.raises(ValueError):
        jobs.control('status', job_id)
    tracked = jobs._jobs[job_id]
    wait_for(lambda: tracked.result is not None)
    assert tracked.result['cancelled'] and tracked.result['returncode'] != 0


def test_close_cancels_and_rejects_new_work(jobs, tmp_path):
    started = tmp_path / 'started'
    job_id = jobs.start(argv(f'import pathlib,time; pathlib.Path({str(started)!r}).touch(); time.sleep(30)'),
                        str(tmp_path), 0)['job_id']
    wait_for(started.exists)
    jobs.close()
    tracked = jobs._jobs[job_id]
    assert tracked.result['cancelled'] and not tracked.thread.is_alive()
    jobs.close()
    with pytest.raises(ValueError, match='closed'):
        jobs.start(argv('print("no")'), str(tmp_path), 0)


@pytest.mark.parametrize('value', [1, 'true', None, [], {}])
def test_background_requires_boolean(active, jobs, tmp_path, value):
    state, record = active
    with pytest.raises(ValueError, match='background'):
        machine.call_local(state, record['id'], 'machine_exec', {
            'argv': argv('print("no")'), 'cwd': str(tmp_path), 'background': value}, jobs=jobs)


def test_one_shot_and_administrator_background_are_explicit_errors(active, jobs, tmp_path):
    state, record = active
    args = {'argv': argv('print("no")'), 'cwd': str(tmp_path), 'background': True}
    with pytest.raises(ValueError, match='MCP session'):
        machine.call_local(state, record['id'], 'machine_exec', args)
    from ballz2thewall.admin import AdminError
    with pytest.raises(AdminError, match='off'):
        machine.call_local(state, record['id'], 'machine_exec', dict(args, administrator=True), jobs=jobs)
    assert jobs.control('list')['jobs'] == []


def test_job_id_and_owner_validation(active, jobs, tmp_path):
    state, record = active
    from ballz2thewall.machine_jobs import CommandJobs
    other = CommandJobs(state, 'e' * 32)
    try:
        with pytest.raises(ValueError, match='session'):
            machine.call_local(state, record['id'], 'machine_job', {'operation': 'list'}, jobs=other)
    finally:
        other.close()
    for operation, job_id in [('status', '../x'), ('cancel', None), ('unknown', None),
                              ('status', 'f' * 32), ('list', 'f' * 32)]:
        with pytest.raises(ValueError):
            jobs.control(operation, job_id)


def test_completed_history_eviction_preserves_active_jobs(jobs, tmp_path, monkeypatch):
    import ballz2thewall.machine_jobs as module
    monkeypatch.setattr(module, 'COMPLETED_HISTORY_LIMIT', 2)
    active_id = jobs.start(argv('import time; time.sleep(30)'), str(tmp_path), 0)['job_id']
    old_id = None
    for _ in range(3):
        job_id = jobs.start(argv('print("history")'), str(tmp_path), 0)['job_id']
        finished(jobs, job_id)
        old_id = old_id or job_id
    listing = jobs.control('list')
    assert len(listing['jobs']) == 3 and listing['evicted_completed'] == 1
    assert active_id in {job['job_id'] for job in listing['jobs']}
    with pytest.raises(ValueError, match='Unknown|expired'):
        jobs.control('status', old_id)


def test_runner_checks_revocation_before_spawn(tmp_path, monkeypatch):
    def no_spawn(*args, **kwargs):
        pytest.fail('revoked command spawned')
    def inactive():
        raise ValueError('OFF')
    monkeypatch.setattr(machine.subprocess, 'Popen', no_spawn)
    with pytest.raises(ValueError, match='OFF'):
        machine.run_command(argv('pass'), str(tmp_path), still_active=inactive)


def test_utf8_split_capture_and_both_stream_limits():
    capture = machine.CommandOutput()
    encoded = '🐉'.encode()
    capture.append(0, encoded[:2])
    capture.append(0, encoded[2:])
    assert capture.snapshot()['stdout'] == '🐉'
    capture.append(0, b'x' * machine.OUTPUT_LIMIT)
    capture.append(1, b'y' * (machine.OUTPUT_LIMIT + 9))
    result = capture.snapshot()
    assert len(result['stdout'].encode()) == machine.OUTPUT_LIMIT
    assert len(result['stderr']) == machine.OUTPUT_LIMIT
    assert result['truncated'] is True


def test_job_handle_is_private_to_original_mcp_session(active, jobs, tmp_path):
    from ballz2thewall.machine_jobs import CommandJobs
    state, record = active
    item = jobs.start(argv('print("owner")'), str(tmp_path))
    with pytest.raises(ValueError, match='different MCP session'):
        jobs.require_owner(tmp_path / 'other', record['id'])
    other = CommandJobs(state, record['id'])
    try:
        with pytest.raises(ValueError, match='Unknown or expired'):
            other.control('status', item['job_id'])
    finally:
        other.close()


def test_thread_start_failure_leaves_no_ghost_job(jobs, tmp_path, monkeypatch):
    import threading
    def unavailable(self):
        raise RuntimeError('cannot start new thread')
    monkeypatch.setattr(threading.Thread, 'start', unavailable)
    with pytest.raises(RuntimeError, match='cannot start'):
        jobs.start(argv('pass'), str(tmp_path))
    assert jobs.control('list')['jobs'] == []


@pytest.mark.skipif(os.name == 'nt', reason='POSIX SIGTERM escalation contract')
def test_cancel_stops_sigterm_ignoring_child(jobs, tmp_path):
    item = jobs.start(argv('import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); '
                          'print("armed",flush=True); time.sleep(30)'), str(tmp_path))
    wait_for(lambda: 'armed' in jobs.control('status', item['job_id'])['stdout'])
    jobs.control('cancel', item['job_id'])
    result = finished(jobs, item['job_id'])
    assert result['status'] == 'cancelled' and result['returncode'] != 0


@pytest.mark.parametrize('failed_reader', [1, 2])
def test_reader_start_failure_reaps_spawned_command(tmp_path, monkeypatch, failed_reader):
    import threading
    spawned = []
    original_popen, original_start = machine.subprocess.Popen, threading.Thread.start
    calls = 0
    def popen(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        spawned.append(process)
        return process
    def start(thread):
        nonlocal calls
        calls += 1
        if calls == failed_reader:
            raise RuntimeError('reader thread unavailable')
        return original_start(thread)
    monkeypatch.setattr(machine.subprocess, 'Popen', popen)
    monkeypatch.setattr(threading.Thread, 'start', start)
    try:
        with pytest.raises(RuntimeError, match='reader thread unavailable'):
            machine.run_command(argv('import time; time.sleep(30)'), str(tmp_path))
        assert len(spawned) == 1 and spawned[0].poll() is not None
        assert spawned[0].stdout.closed and spawned[0].stderr.closed
    finally:
        for process in spawned:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)


@pytest.fixture
def tracked_children(monkeypatch):
    spawned = []
    original = machine.subprocess.Popen

    def track(*args, **kwargs):
        process = original(*args, **kwargs)
        spawned.append(process)
        return process

    monkeypatch.setattr(machine.subprocess, 'Popen', track)
    try:
        yield spawned
    finally:
        # A regression must not leave its deliberately long-lived probe behind.
        for process in spawned:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            for stream in (process.stdout, process.stderr):
                if stream is not None and not stream.closed:
                    stream.close()


def test_huge_timeout_foreground_completes(active, tmp_path, tracked_children):
    state, record = active
    result = machine.call_local(state, record['id'], 'machine_exec', {
        'argv': argv('print("huge deadline")'), 'cwd': str(tmp_path), 'timeout': 10**400})
    assert result['returncode'] == 0 and not result['timed_out']
    assert result['stdout'] == 'huge deadline' + os.linesep
    assert len(tracked_children) == 1 and tracked_children[0].poll() == 0


def test_huge_timeout_foreground_off_reaps_child(active, tmp_path, tracked_children):
    from concurrent.futures import ThreadPoolExecutor
    state, record = active
    started = tmp_path / 'huge-foreground-started'
    code = f'import pathlib,time; pathlib.Path({str(started)!r}).touch(); time.sleep(30)'
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(machine.call_local, state, record['id'], 'machine_exec', {
            'argv': argv(code), 'cwd': str(tmp_path), 'timeout': 10**400})
        try:
            wait_for(lambda: started.exists() or future.done())
        finally:
            Activation(state)._save(dict(record, phase='off'))
        result = future.result(timeout=8)
    assert started.exists()
    assert result['cancelled'] and not result['timed_out']
    assert len(tracked_children) == 1 and tracked_children[0].poll() is not None


@pytest.mark.parametrize('mode', ['complete', 'cancel', 'close', 'off'])
def test_huge_timeout_background_lifecycle(active, jobs, tmp_path, tracked_children, mode):
    state, record = active
    code = 'print("huge deadline",flush=True)'
    if mode != 'complete':
        code += '; import time; time.sleep(30)'
    item = machine.call_local(state, record['id'], 'machine_exec', {
        'argv': argv(code), 'cwd': str(tmp_path), 'timeout': 10**400,
        'background': True}, jobs=jobs)
    job_id = item['job_id']
    if mode == 'complete':
        result = finished(jobs, job_id)
        assert result['status'] == 'completed' and result['returncode'] == 0
    else:
        ready = wait_for(lambda: (r if (r := jobs.control('status', job_id))['status']
                                 != 'running' or 'huge deadline' in r['stdout'] else None))
        assert ready['status'] == 'running'
        if mode == 'cancel':
            jobs.control('cancel', job_id)
            result = finished(jobs, job_id)
        else:
            if mode == 'off':
                Activation(state)._save(dict(record, phase='off'))
            jobs.close()
            result = jobs._jobs[job_id].snapshot()
        assert result['status'] == 'cancelled' and result['cancelled']
    jobs.close()
    assert not result['timed_out'] and 'error' not in result
    assert len(tracked_children) == 1 and tracked_children[0].poll() is not None
    assert tracked_children[0].stdout.closed and tracked_children[0].stderr.closed


@pytest.mark.parametrize('failure', ['clock', 'capture'])
def test_runner_initialization_failure_cannot_orphan(tmp_path, monkeypatch, tracked_children, failure):
    from types import SimpleNamespace

    def fail():
        raise RuntimeError('supervision initialization unavailable')

    if failure == 'clock':
        monkeypatch.setattr(machine, 'time', SimpleNamespace(monotonic=fail, monotonic_ns=fail))
    else:
        monkeypatch.setattr(machine, 'CommandOutput', fail)
    with pytest.raises(RuntimeError, match='supervision initialization unavailable'):
        machine.run_command(argv('import time; time.sleep(30)'), str(tmp_path))
    assert all(process.poll() is not None for process in tracked_children)
    assert all(process.stdout.closed and process.stderr.closed for process in tracked_children)


def test_job_schema_rejects_invalid_operations_and_handles():
    from jsonschema import Draft202012Validator
    tool = next(t for t in machine.local_tools() if t.name == 'machine_job')
    validator = Draft202012Validator(tool.inputSchema)
    for bad in ({'operation': 'status'}, {'operation': 'list', 'job_id': 'a' * 32},
                {'operation': 'cancel', 'job_id': 'bogus'}, {'operation': 'list', 'extra': True}):
        assert list(validator.iter_errors(bad))
    for good in ({'operation': 'list'}, {'operation': 'status', 'job_id': 'a' * 32},
                 {'operation': 'cancel', 'job_id': 'a' * 32}):
        assert not list(validator.iter_errors(good))


@pytest.mark.parametrize('mode', ['complete', 'cancel', 'off', 'disconnect'])
@pytest.mark.parametrize('timeout', [0, 10**400], ids=['unlimited', 'huge-timeout'])
def test_real_stdio_background_lifecycle(active, tmp_path, mode, timeout):
    state, record = active
    started, late = tmp_path / 'started', tmp_path / 'late'
    code = (f'import pathlib,time; pathlib.Path({str(started)!r}).touch(); '
            'print("MCP_PROGRESS",flush=True); time.sleep(2); '
            f'pathlib.Path({str(late)!r}).write_text("MCP_FINISHED"); print("MCP_DONE")')

    async def probe():
        spec = machine.server_spec(state, record['id'])
        spec['args'].append('--no-desktop')
        async with stdio_client(StdioServerParameters(**spec)) as transport:
            async with ClientSession(*transport) as session:
                await session.initialize()
                names = {t.name for t in (await session.list_tools()).tools}
                assert 'machine_job' in names
                response = await asyncio.wait_for(session.call_tool('machine_exec', {
                    'argv': argv(code), 'cwd': str(tmp_path), 'background': True, 'timeout': timeout}), 1.5)
                assert not response.isError
                job_id = json.loads(response.content[0].text)['job_id']
                for _ in range(160):
                    response = await session.call_tool('machine_job', {'operation': 'status', 'job_id': job_id})
                    data = json.loads(response.content[0].text)
                    if 'MCP_PROGRESS' in data['stdout']:
                        break
                    await asyncio.sleep(.025)
                assert not response.isError and 'MCP_PROGRESS' in data['stdout']
                assert started.exists()
                if mode == 'off':
                    record['phase'] = 'stopping'
                    Activation(state)._save(record)
                    await asyncio.sleep(.5)
                elif mode == 'disconnect':
                    pass
                else:
                    if mode == 'cancel':
                        await session.call_tool('machine_job', {'operation': 'cancel', 'job_id': job_id})
                    for _ in range(160):
                        response = await session.call_tool('machine_job', {'operation': 'status', 'job_id': job_id})
                        data = json.loads(response.content[0].text)
                        if data['status'] not in {'running', 'cancelling'}:
                            break
                        await asyncio.sleep(.025)
                    assert data['status'] == ('completed' if mode == 'complete' else 'cancelled')
                    assert response.isError == (mode == 'cancel')
                    if mode == 'complete':
                        assert 'MCP_DONE' in data['stdout'] and data['returncode'] == 0
        if mode != 'complete':
            await asyncio.sleep(2.2)
            assert not late.exists(), 'managed command survived cancellation or transport close'
        else:
            assert late.read_text() == 'MCP_FINISHED'

    asyncio.run(asyncio.wait_for(probe(), 20))
