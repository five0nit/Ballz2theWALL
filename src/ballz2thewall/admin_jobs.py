"""Activation-bound, connection-owned approved-helper commands.

Each background command owns one authenticated loopback connection. EOF is a
cancellation signal, not detachment. No reconnect, persistent handle or service.
The helper reuses machine.run_command and its bounded per-stream CommandOutput.
"""
from __future__ import annotations

import select
import socket
import threading
import time
from pathlib import Path

from . import admin, wire_json
from .machine import CommandOutput, run_command

# Two streams, worst-case JSON escaping, and bounded metadata.
MAX_RESPONSE = 2 * 262144 * 6 + 65536
POLL_INTERVAL = .05


def _send(connection, value, limit=MAX_RESPONSE):
    connection.settimeout(admin.IO_TIMEOUT)
    connection.sendall((wire_json.dumps(value, max_bytes=limit - 1) + '\n').encode())


def _status(result, cancelling=False):
    if result is None:
        return 'cancelling' if cancelling else 'running'
    if result.get('cancelled'):
        return 'cancelled'
    if result.get('timed_out'):
        return 'timed_out'
    if result.get('error') or result.get('returncode', 0) != 0:
        return 'failed'
    return 'completed'


def serve_command(connection, request, revoked, check_gate):
    """Called only after token, activation, command and slot validation."""
    output = CommandOutput()
    cancel = threading.Event()
    result = None
    lock = threading.Lock()

    def active():
        if cancel.is_set() or revoked.is_set():
            raise ValueError('Administrative command cancelled')
        try:
            check_gate()
        except admin.AdminError as exc:
            raise ValueError(str(exc)) from exc

    def run():
        nonlocal result
        try:
            value = run_command(request['argv'], request['cwd'], request['timeout'],
                                still_active=active, output=output)
            value['elevated'] = True  # The server's OS-token gate, never client intent.
        except Exception as exc:
            value = {**output.snapshot(), 'timed_out': False,
                     'cancelled': cancel.is_set() or revoked.is_set(), 'elevated': False,
                     'error': f'Administrative command failed ({type(exc).__name__}); inspect executable, path and OS access'}
        with lock:
            result = value

    worker = threading.Thread(target=run, name='ballz-admin-command', daemon=True)
    worker.start()
    try:
        _send(connection, {'status': 'running', 'elevated': True})
        revocation_deadline = None
        while True:
            if revoked.is_set():
                cancel.set()
                if revocation_deadline is None:
                    revocation_deadline = time.monotonic() + admin.IO_TIMEOUT
                if time.monotonic() >= revocation_deadline:
                    break
            # Poll EOF even when the owner never asks for another snapshot.
            if not select.select([connection], [], [], admin.GATE_POLL_INTERVAL)[0]:
                continue
            if not connection.recv(1, socket.MSG_PEEK):
                break
            message = admin._line(connection, admin.MAX_REQUEST, time.monotonic() + admin.IO_TIMEOUT)
            if set(message) != {'op'} or message['op'] not in ('status', 'cancel'):
                raise admin.AdminError('Malformed administrative job operation')
            if message['op'] == 'cancel':
                cancel.set()
            with lock:
                value = dict(result) if result is not None else {**output.snapshot(), 'elevated': True}
                value['status'] = _status(result, cancel.is_set())
            _send(connection, value)
            if revoked.is_set() and value['status'] not in ('running', 'cancelling'):
                break
    finally:
        cancel.set()
        worker.join(7)
        if worker.is_alive():
            raise admin.AdminError('Administrative direct-child cleanup incomplete')


class RemoteCommand:
    """A local job worker's private socket; no remote job IDs can be transferred."""

    def __init__(self, state: Path, activation_id: str, argv, cwd, timeout):
        admin._validate_command(argv, cwd, timeout)
        endpoint = admin._endpoint(state)
        if endpoint is None:
            raise admin.AdminError('Administrative helper is off')
        if endpoint.get('activation_id') != activation_id:
            raise admin.AdminError('Invalid or stale administrative activation identity')
        admin._require_activation(state, activation_id)
        port, token = endpoint.get('port'), endpoint.get('token')
        if (type(port) is not int or not 1 <= port <= 65535
                or not isinstance(token, str) or len(token) != 64):
            raise admin.AdminError('Invalid administrative endpoint')
        # Encode before connecting; oversized requests never reserve a child.
        payload = {'op': 'job', 'argv': argv, 'cwd': cwd, 'timeout': timeout,
                   'activation_id': activation_id, 'token': token}
        wire = (wire_json.dumps(payload, max_bytes=admin.MAX_REQUEST - 1) + '\n').encode()
        self.connection = None
        try:
            self.connection = socket.create_connection(('127.0.0.1', port), admin.IO_TIMEOUT)
            self.connection.settimeout(admin.IO_TIMEOUT)
            self.connection.sendall(wire)
            result = self._read()
            if result.get('status') != 'running' or result.get('elevated') is not True:
                raise admin.AdminError('Helper did not confirm elevated command ownership')
        except Exception:
            self.close()
            raise

    def _read(self):
        if self.connection is None:
            raise admin.AdminError('Administrative command connection is closed')
        result = admin._line(self.connection, MAX_RESPONSE, time.monotonic() + admin.IO_TIMEOUT)
        if result.get('error') and 'status' not in result:
            raise admin.AdminError(result['error'])
        return result

    def run(self, active, publish):
        cancelling = False
        try:
            while True:
                try:
                    active()
                except (ValueError, OSError):
                    cancelling = True
                _send(self.connection, {'op': 'cancel' if cancelling else 'status'}, admin.MAX_REQUEST)
                value = self._read()
                publish(value)
                if value.get('status') not in ('running', 'cancelling'):
                    return value
                time.sleep(POLL_INTERVAL)
        finally:
            self.close()

    def close(self):
        if self.connection is not None:
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.connection.close()
            self.connection = None
