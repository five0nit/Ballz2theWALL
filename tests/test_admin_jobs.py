"""Real loopback/child tests with injected detection, NOT OS elevation evidence."""
import socket
import sys
import time

import pytest
from test_admin import activation
from test_admin import helper as helper
from test_admin import tracked_children as tracked_children

from ballz2thewall import admin, machine, wire_json


def wait_for(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(.02)
    pytest.fail('scratch helper did not reach expected state')


def request(state, **changes):
    endpoint = admin._endpoint(state)
    value = {'op': 'job', 'argv': [sys.executable, '-I', '-u', '-c', 'print("ok")'],
             'cwd': str(state), 'timeout': 0, 'activation_id': endpoint['activation_id']}
    value.update(changes)
    return value


def connect(state, **changes):
    endpoint = admin._endpoint(state)
    connection = socket.create_connection(('127.0.0.1', endpoint['port']), 2)
    payload = dict(request(state, **changes), token=endpoint['token'])
    connection.sendall((wire_json.dumps(payload) + '\n').encode())
    return connection, admin._line(connection, 4 * 1024 * 1024, time.monotonic() + 3)


def control(connection, operation='status'):
    connection.sendall((wire_json.dumps({'op': operation}) + '\n').encode())
    return admin._line(connection, 4 * 1024 * 1024, time.monotonic() + 3)


def test_owned_connection_live_output_cancel_reuse(helper, tracked_children):
    code = 'import sys,time; print("live",flush=True); print("err",file=sys.stderr,flush=True); time.sleep(30)'
    with connect(helper, argv=[sys.executable, '-I', '-u', '-c', code])[0] as connection:
        partial = wait_for(lambda: (r if 'live' in (r := control(connection)).get('stdout', '') else None))
        assert partial['status'] == 'running' and partial['stderr'].strip() == 'err'
        assert partial['elevated'] is True and 'returncode' not in partial
        control(connection, 'cancel')
        result = wait_for(lambda: (r if (r := control(connection))['status'] == 'cancelled' else None))
        assert result['cancelled'] and result['returncode'] != 0
    assert tracked_children and all(p.poll() is not None for p in tracked_children)
    with connect(helper)[0] as connection:
        result = wait_for(lambda: (r if (r := control(connection))['status'] == 'completed' else None))
        assert result['returncode'] == 0 and result['stdout'].strip() == 'ok'


@pytest.mark.parametrize('change,match', [({'activation_id': 'd'*32}, 'activation'),
    ({'timeout': True}, 'timeout'), ({'extra': True}, 'Malformed'), ({'argv': []}, 'argv')])
def test_background_rejects_bad_authenticated_requests(helper, tracked_children, change, match):
    with pytest.raises(admin.AdminError, match=match):
        admin._request(admin._endpoint(helper), request(helper, **change))
    assert tracked_children == []
    assert admin.status(helper)['status'] == 'ready'


def test_background_wrong_token_never_spawns(helper, tracked_children):
    endpoint = dict(admin._endpoint(helper), token='x'*64)
    with pytest.raises(admin.AdminError, match='Unauthorized'):
        admin._request(endpoint, request(helper))
    assert tracked_children == []


@pytest.mark.parametrize('mode', ['eof', 'stop', 'off', 'rotate', 'malformed'])
def test_owned_connection_cancels_and_reaps_direct_child(helper, tracked_children, mode):
    code = 'import time; print("ready",flush=True); time.sleep(30)'
    connection, ready = connect(helper, argv=[sys.executable, '-I', '-u', '-c', code])
    try:
        assert ready['elevated'] is True
        wait_for(lambda: 'ready' in control(connection).get('stdout', ''))
        assert len(tracked_children) == 1 and tracked_children[0].poll() is None
        if mode == 'eof':
            connection.close()
        elif mode == 'stop':
            assert admin.stop(helper)['status'] == 'off'
        elif mode == 'malformed':
            assert 'error' in control(connection, 'execute')
        else:
            activation(helper, **({'phase': 'off'} if mode == 'off' else {'id': 'd'*32}))
        # Process exit precedes reader-thread EOF cleanup. Require all three
        # outcomes within the same bound instead of racing the stream closers.
        wait_for(lambda: tracked_children[0].poll() is not None
                 and tracked_children[0].stdout.closed
                 and tracked_children[0].stderr.closed)
    finally:
        connection.close()


@pytest.mark.parametrize('timeout', [0, 601, 10**4300], ids=['unlimited', 'positive', 'huge'])
def test_background_bounded_output_timeout_wire_policy(helper, timeout):
    before = sys.get_int_max_str_digits()
    code = 'import os; os.write(1,b"x"*300000); os.write(2,b"\\xff"*300000)'
    with connect(helper, argv=[sys.executable, '-I', '-c', code], timeout=timeout)[0] as connection:
        result = wait_for(lambda: (r if (r := control(connection))['status'] == 'completed' else None))
    assert len(result['stdout']) == machine.OUTPUT_LIMIT
    assert len(result['stderr']) == machine.OUTPUT_LIMIT
    assert result['truncated'] and not result['timed_out']
    assert sys.get_int_max_str_digits() == before


def test_job_slots_leave_stop_responsive_and_all_children_reaped(helper, tracked_children):
    connections = []
    try:
        for _ in range(4):
            connection, ready = connect(helper, argv=[sys.executable, '-u', '-c',
                'import time; print("ready",flush=True); time.sleep(30)'])
            connections.append(connection)
            assert ready['elevated'] is True
            wait_for(lambda: 'ready' in control(connection).get('stdout', ''))
        with pytest.raises(admin.AdminError, match='slots busy'):
            admin._request(admin._endpoint(helper), request(helper))
        before = time.monotonic()
        assert admin.stop(helper)['status'] == 'off'
        assert time.monotonic() - before < 2
        wait_for(lambda: all(p.poll() is not None for p in tracked_children))
        assert len(tracked_children) == 4
    finally:
        for connection in connections:
            connection.close()


def test_background_timeout(helper, tracked_children):
    with connect(helper, argv=[sys.executable, '-c', 'import time; time.sleep(30)'], timeout=1)[0] as connection:
        result = wait_for(lambda: (r if (r := control(connection))['status'] == 'timed_out' else None))
    assert result['timed_out'] and not result['cancelled'] and result['returncode'] != 0
    assert all(p.poll() is not None for p in tracked_children)
