"""Background command ownership for one connected machine MCP session.

Reuse the ordinary command runner, never spawn a daemon or use an agent profile.
Handles/results live in memory; OFF, identity rotation and orderly transport close
cancel the managed parent processes. Escaped descendants remain outside this claim.
"""
from __future__ import annotations

import re
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .admin_jobs import RemoteCommand

from .machine import CommandOutput, require_on, run_command, validate_exec

COMPLETED_HISTORY_LIMIT = 64


@dataclass
class _Job:
    job_id: str
    timeout: int
    created_at: float = field(default_factory=time.time)
    output: CommandOutput = field(default_factory=CommandOutput)
    cancel: threading.Event = field(default_factory=threading.Event)
    result: dict | None = None
    thread: threading.Thread | None = None
    remote: RemoteCommand | None = None
    remote_snapshot: dict | None = None

    def snapshot(self, *, include_output: bool = True) -> dict:
        status = 'cancelling' if self.cancel.is_set() else 'running'
        if self.result is not None:
            if self.result.get('cancelled'):
                status = 'cancelled'
            elif self.result.get('timed_out'):
                status = 'timed_out'
            elif self.result.get('error') or self.result.get('returncode', 0) != 0:
                status = 'failed'
            else:
                status = 'completed'
        summary = {'job_id': self.job_id, 'status': status,
                   'created_at': self.created_at, 'timeout': self.timeout}
        if self.remote is not None:
            summary.update(administrator=True, elevated=(self.result or self.remote_snapshot or {}).get('elevated', True))
        if include_output:
            captured = self.result if self.result is not None else (self.remote_snapshot or self.output.snapshot())
            return {**summary, **captured, 'status': status}
        return summary


class CommandJobs:
    """A lock owns job registration, cancellation, snapshots and history eviction."""

    def __init__(self, state: Path, activation_id: str):
        self.state = state.expanduser().absolute()
        self.activation_id = activation_id
        self._closed = threading.Event()
        self._lock = threading.Lock()
        self._jobs: dict[str, _Job] = {}
        self._completed: deque[str] = deque()
        self._evicted = 0

    def require_owner(self, state: Path, activation_id: str) -> None:
        if state.expanduser().absolute() != self.state or activation_id != self.activation_id:
            raise ValueError('Command jobs belong to a different MCP session activation')
        self._active()

    def _active(self) -> None:
        if self._closed.is_set():
            raise ValueError('Command job session is closed')
        try:
            require_on(self.state, self.activation_id)
        except (ValueError, OSError):
            # An observed revocation is irreversible for this session.
            self._closed.set()
            raise

    def start(self, argv: list[str], cwd: str, timeout: int = 0, *, administrator: bool = False) -> dict:
        argv, directory, timeout = validate_exec(argv, cwd, timeout)
        self._active()
        job = _Job(uuid.uuid4().hex, timeout)
        command = list(argv)  # Caller mutation cannot change a queued command.
        with self._lock:
            self._active()
            if type(administrator) is not bool:
                raise ValueError('administrator must be boolean')
            if administrator:
                from .admin_jobs import RemoteCommand
                job.remote = RemoteCommand(self.state, self.activation_id, command, str(directory), timeout)
            try:
                job.thread = threading.Thread(target=self._run, args=(job, command, str(directory)),
                                              name='ballz-job-' + job.job_id[:8], daemon=True)
                self._jobs[job.job_id] = job
                job.thread.start()
            except Exception:
                self._jobs.pop(job.job_id, None)
                if job.remote is not None:
                    job.remote.close()
                raise
            return job.snapshot()

    def _run(self, job: _Job, argv: list[str], cwd: str) -> None:
        def active():
            if job.cancel.is_set():
                raise ValueError('Command job cancellation requested')
            self._active()

        try:
            if job.remote is not None:
                def publish(value):
                    with self._lock:
                        job.remote_snapshot = value
                result = job.remote.run(active, publish)
            else:
                result = run_command(argv, cwd, job.timeout, still_active=active, output=job.output)
        except Exception as exc:
            # Keep spawn/runtime failures inspectable without quoting argv/paths.
            try:
                self._active()
            except (ValueError, OSError):
                pass
            result = {**(job.remote_snapshot or job.output.snapshot()), 'timed_out': False,
                      'cancelled': job.cancel.is_set() or self._closed.is_set(),
                      'error': f'Machine command failed ({type(exc).__name__}); inspect executable, path and OS access',
                      'elevated': False}
        with self._lock:
            job.result = result
            self._completed.append(job.job_id)
            while len(self._completed) > COMPLETED_HISTORY_LIMIT:
                del self._jobs[self._completed.popleft()]
                self._evicted += 1

    def control(self, operation: str, job_id: str | None = None) -> dict:
        self._active()
        if operation not in ('list', 'status', 'cancel'):
            raise ValueError('operation must be list, status or cancel')
        if operation == 'list' and job_id is not None:
            raise ValueError('list does not accept job_id')
        with self._lock:
            if operation == 'list':
                return {'jobs': [j.snapshot(include_output=False) for j in self._jobs.values()],
                        'evicted_completed': self._evicted,
                        'completed_history_limit': COMPLETED_HISTORY_LIMIT,
                        'lifetime': 'connected MCP session; OFF/disconnect cancels managed commands'}
            if not isinstance(job_id, str) or not re.fullmatch(r'[0-9a-f]{32}', job_id):
                raise ValueError('job_id must be the exact 32-character identifier returned by machine_exec')
            if job_id not in self._jobs:
                raise ValueError('Unknown or expired job_id in this MCP session')
            job = self._jobs[job_id]
            if operation == 'cancel' and job.result is None:
                job.cancel.set()
            return job.snapshot()

    def close(self) -> None:
        """Latch shutdown before joining; no late starts, no live-activation reads."""
        with self._lock:
            self._closed.set()
            threads = [j.thread for j in self._jobs.values() if j.thread is not None]
        deadline = time.monotonic() + 8
        for thread in threads:
            thread.join(timeout=max(0, deadline - time.monotonic()))
        if any(thread.is_alive() for thread in threads):
            raise RuntimeError('Managed command cleanup incomplete; job worker did not stop')
