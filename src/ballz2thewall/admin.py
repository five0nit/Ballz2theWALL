"""Explicitly approved, same-user Windows administrator helper.

The bearer token intentionally grants arbitrary command execution. OFF revokes
new work and terminates only the direct running child; it cannot undo actions or
promise descendant cleanup. No service, firewall rule or UAC policy is installed.
"""
from __future__ import annotations

import argparse
import base64
import hmac
import json
import math
import os
import secrets
import select
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import platform_store, wire_json
from .store import Store, atomic_write

WINDOWS = sys.platform == "win32"
MAX_REQUEST = 64 * 1024
MAX_OUTPUT = 256 * 1024
MAX_RESPONSE = MAX_OUTPUT * 6 + 4096
IO_TIMEOUT = 3.0
GATE_POLL_INTERVAL = 0.1


class AdminError(RuntimeError):
    """The helper could not authenticate or complete a request."""


def _identity() -> str:
    if not WINDOWS:
        raise AdminError("Native administrative approval requires Windows")
    return platform_store.current_user_sid()


def _elevated() -> bool:
    if not WINDOWS:
        return False
    import ctypes
    return bool(ctypes.windll.shell32.IsUserAnAdmin())


def _store(state: Path) -> Store:
    return Store(Path(state).expanduser().absolute() / "admin")


def _read(path: Path) -> dict | None:
    platform_store.validate_path(path)
    if not path.exists():
        return None
    with path.open("rb") as stream:
        data = stream.read(MAX_REQUEST + 1)
    if len(data) > MAX_REQUEST:
        raise AdminError("Administrative state is oversized")
    result = json.loads(data)
    if not isinstance(result, dict):
        raise AdminError("Invalid administrative state")
    return result


def _save(path: Path, value: dict) -> None:
    atomic_write(path, json.dumps(value).encode("utf-8"))


def _line(sock: socket.socket, limit: int, deadline: float | None, *,
          deadline_ns: int | None = None) -> dict:
    # Preserve the seconds-based private interface; command responses use exact
    # integer nanoseconds so accepted command lifetimes never overflow floats.
    if deadline_ns is None and deadline is not None:
        deadline_ns = int(deadline * 1_000_000_000)
    data = bytearray()
    while True:
        remaining = deadline_ns - time.monotonic_ns() if deadline_ns is not None else None
        if remaining is not None and remaining <= 0:
            raise AdminError("Administrative socket deadline exceeded")
        # Cap individual socket waits, never the command's lifetime. Convert to
        # float only after bounding to a platform-safe interval.
        sock.settimeout(min(remaining, int(IO_TIMEOUT * 1_000_000_000)) / 1_000_000_000
                        if remaining is not None else None)
        try:
            chunk = sock.recv(min(4096, limit + 1 - len(data)))
        except socket.timeout:
            if deadline_ns is None:
                raise
            continue  # Recheck the original deadline, not a renewed one.
        if not chunk:
            raise AdminError("Incomplete administrative response")
        data.extend(chunk)
        if len(data) > limit:
            raise AdminError("Administrative message exceeds size limit")
        if b"\n" in chunk:
            line, trailing = bytes(data).split(b"\n", 1)
            if trailing:
                raise AdminError("Only one JSON message is permitted")
            value = wire_json.loads(line, max_bytes=limit)
            if not isinstance(value, dict):
                raise AdminError("Administrative message must be an object")
            return value


def _request(endpoint: dict, payload: dict, timeout: int | float | None = IO_TIMEOUT) -> dict:
    port, token = endpoint.get("port"), endpoint.get("token")
    if (type(port) is not int or not 1 <= port <= 65535
            or not isinstance(token, str) or len(token) != 64):
        raise AdminError("Invalid administrative endpoint")
    try:
        wire = (wire_json.dumps({**payload, "token": token}, max_bytes=MAX_REQUEST - 1) + "\n").encode()
    except ValueError as exc:
        raise AdminError(f"Administrative request invalid: {exc}") from exc
    try:
        with socket.create_connection(("127.0.0.1", port), IO_TIMEOUT) as sock:
            sock.settimeout(IO_TIMEOUT)
            sock.sendall(wire)
            deadline_ns = (time.monotonic_ns() + int(timeout * 1_000_000_000)
                           if timeout is not None else None)
            result = _line(sock, MAX_RESPONSE, None, deadline_ns=deadline_ns)
    except (OSError, ValueError) as exc:
        raise AdminError(f"Administrative helper unavailable: {exc}") from exc
    if result.get("error"):
        raise AdminError(result["error"])
    return result


def _endpoint(state: Path) -> dict | None:
    store = _store(state)
    if not store.root.exists():
        return None
    with store.lock():
        return _read(store.root / "endpoint.json")


def _require_activation(state: Path, activation_id: object) -> dict:
    # require_on reads the atomic controller record without taking its lock.
    # OFF can hold that lock while calling disable: never acquire it here.
    from .machine import require_on
    if not isinstance(activation_id, str):
        raise AdminError("Invalid machine activation identity")
    try:
        return require_on(state, activation_id)
    except (ValueError, OSError) as exc:
        raise AdminError(str(exc)) from exc


def _process_exited(pid: object) -> bool:
    """Only positively identify dead processes; access denied/reused PIDs stay live."""
    if type(pid) is not int or not 0 < pid <= 0xFFFFFFFF:
        return False
    if not WINDOWS:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except OSError:
            pass
        return False
    # Never use os.kill(pid, 0) on Windows: it can terminate the process.
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE, no termination rights.
    if not handle:
        return ctypes.get_last_error() == 87  # ERROR_INVALID_PARAMETER: no such PID.
    try:
        return kernel.WaitForSingleObject(handle, 0) == 0  # WAIT_OBJECT_0 (exited).
    finally:
        kernel.CloseHandle(handle)


def _remove_stale_endpoint(state: Path, endpoint: dict) -> bool:
    """Recover only a dead PID AND refused loopback port; preserve uncertainty."""
    port = endpoint.get("port")
    if type(port) is not int or not 1 <= port <= 65535 or not _process_exited(endpoint.get("pid")):
        return False
    try:
        with socket.create_connection(("127.0.0.1", port), IO_TIMEOUT):
            return False  # Something still listens, even if its token/status changed.
    except ConnectionRefusedError:
        pass
    except OSError:
        return False
    store = _store(state)
    with store.lock():
        if _read(store.root / "endpoint.json") != endpoint:
            return False
        (store.root / "endpoint.json").unlink()
    return True


def status(state: Path) -> dict:
    try:
        endpoint = _endpoint(state)
        if endpoint is None:
            store = _store(state)
            if store.root.exists():
                with store.lock():
                    pending = _read(store.root / "pending.json")
                if pending is not None:
                    return {"status": "pending", "elevated": False,
                            "error": "Approval pending; finish the Windows prompt or explicitly cancel and retry"}
            return {"status": "off" if WINDOWS else "unavailable", "elevated": False}
        _require_activation(state, endpoint.get("activation_id"))
        result = _request(endpoint, {"op": "status"})
        if result.get("status") != "ready" or result.get("elevated") is not True:
            raise AdminError("Helper is not elevated and ready")
        return result
    except (OSError, ValueError, AdminError) as exc:
        return {"status": "unavailable", "elevated": False, "error": str(exc)}


def _ps_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _launch(state: Path, sid: str, launch_id: str) -> None:
    # Start-Process joins ArgumentList itself: supply one CRT-quoted string.
    argv = ["-I", "-m", "ballz2thewall.admin", "--serve", "--state-dir", str(state),
            "--expected-sid", sid, "--launch-id", launch_id]
    script = ("$ErrorActionPreference='Stop'; Start-Process -Verb RunAs -FilePath "
              + _ps_literal(sys.executable) + " -ArgumentList "
              + _ps_literal(subprocess.list2cmdline(argv)) + " -PassThru | Out-Null")
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    powershell = str(Path(system_root) / "System32/WindowsPowerShell/v1.0/powershell.exe")
    subprocess.run([powershell, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                   check=True, capture_output=True, timeout=120)


def start(state: Path) -> dict:
    if not WINDOWS:
        return {"status": "unavailable", "elevated": False,
                "error": "Native administrative approval requires Windows"}
    state = Path(state).expanduser().absolute()
    store = _store(state)
    launch_id = secrets.token_hex(32)
    try:
        from .onboarding import Activation
        activation_id = Activation(state).status().get("id")
        _require_activation(state, activation_id)
        sid = _identity()
        endpoint = _endpoint(state)
        if endpoint is not None and not _remove_stale_endpoint(state, endpoint):
            if endpoint.get("sid") != sid:
                raise AdminError("Existing helper SID differs; endpoint preserved")
            return status(state)
        with store.lock():
            _require_activation(state, activation_id)
            endpoint = _read(store.root / "endpoint.json")
            if endpoint is not None:
                raise AdminError("Existing helper state preserved")
            if _read(store.root / "pending.json") is not None:
                raise AdminError("Approval already pending; existing state preserved")
            _save(store.root / "pending.json", {"sid": sid, "launch_id": launch_id,
                                                "activation_id": activation_id})
        try:
            _launch(state, sid, launch_id)
        except subprocess.TimeoutExpired as exc:
            raise AdminError("Approval timed out; pending state preserved") from exc
        except (OSError, subprocess.CalledProcessError) as exc:
            with store.lock():
                pending = _read(store.root / "pending.json")
                if pending and pending.get("launch_id") == launch_id:
                    (store.root / "pending.json").unlink()
            raise AdminError("Administrative approval cancelled or failed") from exc
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            _require_activation(state, activation_id)
            if _endpoint(state) is not None:
                return status(state)
            time.sleep(0.1)
        raise AdminError("Approved helper did not register; pending state preserved")
    except (OSError, ValueError, AdminError) as exc:
        return {"status": "unavailable", "elevated": False, "error": str(exc)}


def stop(state: Path) -> dict:
    try:
        store = _store(state)
        if not store.root.exists():
            return {"status": "off", "elevated": False}
        with store.lock():
            endpoint = _read(store.root / "endpoint.json")
            # Revokes an outstanding approval before it can register.
            pending = store.root / "pending.json"
            if pending.exists():
                pending.unlink()
        if endpoint is None:
            return {"status": "off", "elevated": False}
        try:
            result = _request(endpoint, {"op": "stop"})
        except AdminError:
            # The activation watchdog may have completed revocation first.
            if _endpoint(state) is None or _remove_stale_endpoint(state, endpoint):
                return {"status": "off", "elevated": False, "descendants_terminated": False}
            raise
        if result.get("status") != "off":
            raise AdminError("Helper did not acknowledge revocation")
        return result
    except (OSError, ValueError, AdminError) as exc:
        return {"status": "unavailable", "elevated": False, "error": str(exc)}


def enable(state: Path) -> dict:
    """Controller-facing alias for explicitly approved helper startup."""
    return start(state)


def disable(state: Path) -> dict:
    """Controller-facing revocation, permitted even while OFF/restoring."""
    return stop(state)


def _validate_command(argv: list[str], cwd: str, timeout: int) -> None:
    if (not isinstance(argv, list) or not 1 <= len(argv) <= 256
            or any(not isinstance(arg, str) or "\0" in arg or len(arg) > 32768 for arg in argv)
            or not argv[0]):
        raise AdminError("argv must be a nonempty bounded list of NUL-free strings")
    if (not isinstance(cwd, str) or not cwd or "\0" in cwd or len(cwd) > 32768
            or not Path(cwd).is_absolute() or not Path(cwd).is_dir()):
        raise AdminError("cwd must be an existing absolute directory")
    if type(timeout) is not int or timeout < 0:
        raise AdminError("timeout must be a nonnegative integer; 0 means no deadline")


def execute(state: Path, argv: list[str], cwd: str, timeout: int = 120) -> dict:
    _validate_command(argv, cwd, timeout)
    endpoint = _endpoint(state)
    if endpoint is None:
        raise AdminError("Administrative helper is off")
    activation_id = endpoint.get("activation_id")
    _require_activation(state, activation_id)
    return _request(endpoint, {"op": "execute", "argv": argv, "cwd": cwd, "timeout": timeout,
                               "activation_id": activation_id},
                    timeout + math.ceil(IO_TIMEOUT) + 2 if timeout else None)


def _available(pipe) -> int:
    if not WINDOWS:
        return 4096 if select.select([pipe], [], [], 0)[0] else 0
    import ctypes
    import msvcrt
    from ctypes import wintypes
    available = wintypes.DWORD()
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    peek = kernel.PeekNamedPipe
    peek.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                     ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    peek.restype = wintypes.BOOL
    if not peek(msvcrt.get_osfhandle(pipe.fileno()), None, 0, None, ctypes.byref(available), None):
        if ctypes.get_last_error() == 109:  # ERROR_BROKEN_PIPE
            return 0
        raise ctypes.WinError(ctypes.get_last_error())
    return min(4096, available.value)


def _run_command(argv: list[str], cwd: str, timeout: int, revoked: threading.Event) -> dict:
    if revoked.is_set():
        raise AdminError("Administrative helper revoked")
    output = [bytearray(), bytearray()]
    reason = None
    process = subprocess.Popen(argv, cwd=cwd, shell=False, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
    try:
        deadline = time.monotonic_ns() + timeout * 1_000_000_000 if timeout else None
        while True:
            progress = False
            for index, pipe in enumerate((process.stdout, process.stderr)):
                available = _available(pipe)
                if available:
                    chunk = os.read(pipe.fileno(), available)
                    progress |= bool(chunk)
                    room = MAX_OUTPUT - sum(map(len, output))
                    output[index].extend(chunk[:room])
                    if len(chunk) > room:
                        reason = "output_limit"
            if revoked.is_set():
                reason = "revoked"
            elif deadline is not None and time.monotonic_ns() >= deadline:
                reason = "timeout"
            if reason:
                if process.poll() is None:
                    process.kill()  # Direct child only; never claim a process-tree kill.
                process.wait(timeout=2)
                break
            if process.poll() is not None and not progress:
                break  # Do not wait on pipes inherited by surviving descendants.
            if not progress:
                time.sleep(0.01)
        return {"returncode": process.returncode,
                "stdout": output[0].decode("utf-8", "replace"),
                "stderr": output[1].decode("utf-8", "replace"),
                "timed_out": reason == "timeout", "truncated": reason == "output_limit",
                "revoked": reason == "revoked"}
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)
        process.stdout.close()
        process.stderr.close()


def _serve(state: Path, expected_sid: str, launch_id: str, *,
           elevation_detector=_elevated, identity_detector=_identity,
           command_runner=_run_command) -> None:
    """Internal injectable seam; no CLI elevation bypass exists."""
    if not elevation_detector():
        raise AdminError("--serve requires an elevated Windows administrator token")
    if identity_detector() != expected_sid:
        raise AdminError("Approval must use the requesting user's SID, not another administrator")
    store = _store(state)
    revoked = threading.Event()
    gate = threading.Lock()
    execution = threading.Lock()
    slots = threading.BoundedSemaphore(8)
    # Leave request slots available for status/OFF while jobs hold sockets.
    job_slots = threading.BoundedSemaphore(4)
    endpoint = None
    workers = []
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind(("127.0.0.1", 0))
        listener.listen(8)
        listener.settimeout(GATE_POLL_INTERVAL)
        with store.lock():
            pending = _read(store.root / "pending.json")
            if (pending is None or set(pending) != {"sid", "launch_id", "activation_id"}
                    or pending.get("sid") != expected_sid or pending.get("launch_id") != launch_id):
                raise AdminError("Approval reservation missing, changed or revoked")
            activation_id = pending["activation_id"]
            _require_activation(state, activation_id)
            if _read(store.root / "endpoint.json") is not None:
                raise AdminError("Existing helper state preserved")
            endpoint = {"port": listener.getsockname()[1], "token": secrets.token_hex(32),
                        "pid": os.getpid(), "sid": expected_sid, "launch_id": launch_id,
                        "activation_id": activation_id}
            _save(store.root / "endpoint.json", endpoint)
            (store.root / "pending.json").unlink()

        def check_gate():
            if revoked.is_set():
                raise AdminError("Administrative helper revoked")
            try:
                _require_activation(state, activation_id)
            except AdminError:
                revoked.set()
                raise

        def handle(connection):
            try:
                with connection:
                    try:
                        request = _line(connection, MAX_REQUEST, time.monotonic() + IO_TIMEOUT)
                        token = request.pop("token", None)
                        if (not isinstance(token, str) or not token.isascii()
                                or not hmac.compare_digest(token, endpoint["token"])):
                            raise AdminError("Unauthorized administrative token")
                        operation = request.get("op")
                        with gate:
                            if operation == "stop" and set(request) == {"op"}:
                                revoked.set()
                                with store.lock():
                                    if _read(store.root / "endpoint.json") == endpoint:
                                        (store.root / "endpoint.json").unlink()
                                response = {"status": "off", "elevated": False,
                                            "descendants_terminated": False}
                            elif operation == "status" and set(request) == {"op"}:
                                check_gate()
                                response = {"status": "ready", "elevated": True}
                            elif operation == "execute" and set(request) == {
                                    "op", "argv", "cwd", "timeout", "activation_id"}:
                                if request["activation_id"] != activation_id:
                                    raise AdminError("Invalid or stale administrative activation identity")
                                check_gate()
                                _validate_command(request["argv"], request["cwd"], request["timeout"])
                                if not execution.acquire(blocking=False):
                                    raise AdminError("Administrative helper busy")
                                response = None
                            elif operation == "job" and set(request) == {
                                    "op", "argv", "cwd", "timeout", "activation_id"}:
                                if request["activation_id"] != activation_id:
                                    raise AdminError("Invalid or stale administrative activation identity")
                                check_gate()
                                _validate_command(request["argv"], request["cwd"], request["timeout"])
                                if not job_slots.acquire(blocking=False):
                                    raise AdminError("Administrative background command slots busy")
                                response = None
                            else:
                                raise AdminError("Malformed administrative operation")
                        if response is None:
                            if operation == "job":
                                from .admin_jobs import serve_command
                                try:
                                    serve_command(connection, request, revoked, check_gate)
                                finally:
                                    job_slots.release()
                                return
                            try:
                                with gate:
                                    check_gate()
                                response = command_runner(request["argv"], request["cwd"],
                                                          request["timeout"], revoked)
                            finally:
                                execution.release()
                    except (OSError, ValueError, AdminError, subprocess.SubprocessError) as exc:
                        response = {"error": str(exc)[:1024]}
                    connection.settimeout(IO_TIMEOUT)
                    connection.sendall((wire_json.dumps(response, max_bytes=MAX_RESPONSE - 1) + "\n").encode())
            except OSError:
                pass
            finally:
                slots.release()

        while not revoked.is_set():
            try:
                with gate:
                    check_gate()
            except AdminError:
                break
            try:
                connection, _ = listener.accept()
            except socket.timeout:
                continue
            if not slots.acquire(blocking=False):
                connection.close()
                continue
            workers = [worker for worker in workers if worker.is_alive()]
            worker = threading.Thread(target=handle, args=(connection,), daemon=True)
            workers.append(worker)
            worker.start()
    finally:
        revoked.set()
        listener.close()
        # Keep the process alive until the stop ACK and command result are sent.
        deadline = time.monotonic() + IO_TIMEOUT + 3
        for worker in workers:
            worker.join(max(0, deadline - time.monotonic()))
        # Only remove our own registration; failed/duplicate starts preserve old state.
        if endpoint is not None:
            with store.lock():
                if _read(store.root / "endpoint.json") == endpoint:
                    (store.root / "endpoint.json").unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true", required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--expected-sid", required=True)
    parser.add_argument("--launch-id", required=True)
    args = parser.parse_args(argv)
    try:
        _serve(args.state_dir, args.expected_sid, args.launch_id)
    except (OSError, ValueError, AdminError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
