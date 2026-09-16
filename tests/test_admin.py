"""Scratch-only helper checks: no native approval or host configuration changes."""
from __future__ import annotations

import base64
import ctypes
import json
import os
import socket
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from ballz2thewall import admin
from ballz2thewall.onboarding import Activation


def activation(state, **changes):
    record = {"schema": 1, "id": "a" * 32, "phase": "on", "adapter": "hermes",
              "home": str(state), "after_sha256": "b" * 64, "receipt_id": "c" * 32,
              "machine_access": True}
    record.update(changes)
    controller = Activation(state)
    admin.platform_store.prepare_state_directory(controller.root)
    controller._save(record)
    return record


def reservation(state, sid="test-sid", launch_id="test-launch"):
    record = activation(state)
    store = admin._store(state)
    with store.lock():
        admin._save(store.root / "pending.json", {"sid": sid, "launch_id": launch_id,
                                                "activation_id": record["id"]})
    return store


@pytest.fixture
def helper(tmp_path, tracked_children):
    reservation(tmp_path)
    errors = []

    def run():
        try:
            admin._serve(tmp_path, "test-sid", "test-launch",
                         elevation_detector=lambda: True, identity_detector=lambda: "test-sid")
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 3
    while admin.status(tmp_path)["status"] != "ready":
        assert not errors
        assert time.monotonic() < deadline
        time.sleep(0.01)
    yield tmp_path
    admin.stop(tmp_path)
    thread.join(4)
    assert not thread.is_alive()
    assert not errors


def raw(state, data):
    endpoint = admin._endpoint(state)
    with socket.create_connection(("127.0.0.1", endpoint["port"]), 2) as connection:
        connection.sendall(data)
        return admin._line(connection, admin.MAX_RESPONSE, time.monotonic() + 3)


def test_roundtrip_and_stop(helper):
    result = admin.execute(helper, [sys.executable, "-c", "print('scratch roundtrip')"], str(helper))
    assert result == {"returncode": 0, "stdout": "scratch roundtrip" + os.linesep, "stderr": "",
                      "timed_out": False, "truncated": False, "revoked": False}
    assert admin.status(helper) == {"status": "ready", "elevated": True}
    assert admin.stop(helper)["status"] == "off"
    assert admin._endpoint(helper) is None
    with pytest.raises(admin.AdminError, match="off"):
        admin.execute(helper, [sys.executable], str(helper))


def test_unauthorized_and_wrong_endpoint_token(helper):
    response = raw(helper, b'{"op":"execute","token":"wrong"}\n')
    assert "Unauthorized" in response["error"]
    endpoint = admin._endpoint(helper)
    endpoint["token"] = "x" * 64
    with pytest.raises(admin.AdminError, match="Unauthorized"):
        admin._request(endpoint, {"op": "status"})
    assert admin.status(helper)["status"] == "ready"


@pytest.mark.parametrize("wire", [b"[]\n", b"{oops}\n", b"{}\n{}\n"])
def test_malformed_payload(helper, wire):
    assert "error" in raw(helper, wire)
    assert admin.status(helper)["status"] == "ready"


def test_authenticated_bad_operation(helper):
    with pytest.raises(admin.AdminError, match="Malformed"):
        admin._request(admin._endpoint(helper), {"op": "execute", "argv": []})


def test_oversized_input(helper):
    assert "size limit" in raw(helper, b"x" * (admin.MAX_REQUEST + 1))["error"]
    with pytest.raises(admin.AdminError, match="size limit"):
        admin._request(admin._endpoint(helper), {"op": "status", "extra": "x" * admin.MAX_REQUEST})


def test_bounded_both_output_streams(helper):
    code = "import os\nfor i in range(2000):\n os.write(1,b'x'*4096); os.write(2,b'y'*4096)"
    result = admin.execute(helper, [sys.executable, "-c", code], str(helper))
    assert result["truncated"]
    assert len(result["stdout"]) + len(result["stderr"]) <= admin.MAX_OUTPUT


def test_timeout(helper):
    started = time.monotonic()
    result = admin.execute(helper, [sys.executable, "-c", "import time;time.sleep(10)"], str(helper), 1)
    assert result["timed_out"]
    assert time.monotonic() - started < 4


@pytest.mark.parametrize("timeout", [120, 10**400], ids=["ordinary", "huge"])
def test_stop_responsive_during_command(helper, timeout):
    result = []
    thread = threading.Thread(target=lambda: result.append(admin.execute(
        helper, [sys.executable, "-c", "import time;time.sleep(10)"], str(helper), timeout)))
    thread.start()
    time.sleep(0.1)
    started = time.monotonic()
    assert admin.stop(helper)["status"] == "off"
    assert time.monotonic() - started < 2
    thread.join(3)
    assert result[0]["revoked"]


@pytest.mark.parametrize("argv,cwd,timeout", [([], ".", 1), ([1], ".", 1),
                         (["x\0"], ".", 1), (["x"], ".", 1), (["x"], "/", True),
                         (["x"], "/", -1), (["x"], "/", "601")])
def test_command_validation(argv, cwd, timeout):
    with pytest.raises(admin.AdminError):
        admin._validate_command(argv, cwd, timeout)


def test_process_error_keeps_helper_alive(helper):
    with pytest.raises(admin.AdminError):
        admin.execute(helper, [str(helper / "missing-executable")], str(helper))
    assert admin.status(helper)["status"] == "ready"


@pytest.mark.parametrize("timeout", [0, 601, 86400])
def test_machine_admin_timeout_contract_roundtrip(helper, timeout):
    from ballz2thewall import machine
    result = machine.call_local(helper, Activation(helper).status()["id"], "machine_exec", {
        "argv": [sys.executable, "-I", "-c", "import time; time.sleep(0.15); print('admin contract')"],
        "cwd": str(helper), "administrator": True, "timeout": timeout})
    assert result["returncode"] == 0
    assert result["stdout"] == "admin contract" + os.linesep
    assert not result["timed_out"] and not result["revoked"]


@pytest.mark.parametrize("exponent", [400, 4299, 4300, 6500])
def test_machine_admin_decimal_boundary_roundtrip(helper, tracked_children, exponent):
    from ballz2thewall import machine
    before = sys.get_int_max_str_digits()
    timeout = 10 ** exponent
    result = machine.call_local(helper, Activation(helper).status()["id"], "machine_exec", {
        "argv": [sys.executable, "-I", "-c", "print('BOUNDARY_OK')"],
        "cwd": str(helper), "administrator": True, "timeout": timeout})
    assert result["returncode"] == 0
    assert result["stdout"] == "BOUNDARY_OK" + os.linesep
    assert not result["timed_out"] and not result["revoked"]
    assert tracked_children and all(child.poll() is not None for child in tracked_children)
    assert sys.get_int_max_str_digits() == before


def test_admin_oversized_decimal_request_never_spawns(helper, tracked_children):
    with pytest.raises(admin.AdminError, match="size limit"):
        admin.execute(helper, [sys.executable, "-I", "-c", "print('must not spawn')"], str(helper), 10**66000)
    assert tracked_children == []
    assert admin.status(helper)["status"] == "ready"


def test_admin_raw_bounded_decimal_request(helper, tracked_children):
    endpoint = admin._endpoint(helper)
    request = {"op": "execute", "argv": [sys.executable, "-I", "-c", "print('RAW_OK')"],
               "cwd": str(helper), "activation_id": Activation(helper).status()["id"],
               "token": endpoint["token"]}
    wire = (json.dumps(request)[:-1] + ',"timeout":1' + '0' * 4300 + '}\n').encode()
    assert len(wire) < admin.MAX_REQUEST
    response = raw(helper, wire)
    assert response["returncode"] == 0
    assert response["stdout"] == "RAW_OK" + os.linesep
    assert tracked_children and all(child.poll() is not None for child in tracked_children)


@pytest.mark.parametrize("timeout,wire_timeout", [(0, None), (601, 606.0)])
def test_admin_command_response_deadline_matches_contract(helper, monkeypatch, timeout, wire_timeout):
    calls = []
    with monkeypatch.context() as patch:
        patch.setattr(admin, "_request", lambda *args: calls.append(args) or {"returncode": 0})
        admin.execute(helper, [sys.executable], str(helper), timeout)
    assert calls[0][1]["timeout"] == timeout
    assert calls[0][2] == wire_timeout


@pytest.fixture
def tracked_children(monkeypatch):
    """Reap scratch children even when the regression leaks them on RED."""
    children = []
    original = admin.subprocess.Popen

    def spawn(*args, **kwargs):
        child = original(*args, **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(admin.subprocess, "Popen", spawn)
    yield children
    for child in children:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=3)
        for pipe in (child.stdout, child.stderr):
            if pipe is not None:
                pipe.close()
    assert all(child.poll() is not None for child in children)


@pytest.mark.parametrize("timeout", [10**20, 10**400], ids=["platform-range", "float-overflow"])
def test_huge_timeout_runner_completes(tmp_path, tracked_children, timeout):
    result = admin._run_command([sys.executable, "-I", "-c", "print('huge timeout')"],
                                str(tmp_path), timeout, threading.Event())
    assert result["returncode"] == 0
    assert result["stdout"] == "huge timeout" + os.linesep
    assert not result["timed_out"] and not result["revoked"]
    assert tracked_children[0].poll() == 0
    assert tracked_children[0].stdout.closed and tracked_children[0].stderr.closed


def test_huge_timeout_runner_revocation(tmp_path, tracked_children):
    revoked = threading.Event()
    timer = threading.Timer(0.15, revoked.set)
    timer.start()
    try:
        result = admin._run_command([sys.executable, "-I", "-c", "import time; time.sleep(30)"],
                                    str(tmp_path), 10**400, revoked)
        assert result["revoked"] and not result["timed_out"]
        assert result["returncode"] != 0
        assert tracked_children[0].poll() is not None
    finally:
        timer.cancel()
        timer.join(2)


def test_post_spawn_clock_failure_reaps_child(tmp_path, monkeypatch, tracked_children):
    def fail_clock():
        assert tracked_children, "clock must initialize after spawning"
        raise RuntimeError("injected deadline initialization failure")

    # Replace only this module's clock, not subprocess's shared time module.
    monkeypatch.setattr(admin, "time", SimpleNamespace(monotonic=fail_clock, monotonic_ns=fail_clock))
    with pytest.raises(RuntimeError, match="injected deadline"):
        admin._run_command([sys.executable, "-I", "-c", "import time; time.sleep(30)"],
                           str(tmp_path), 1, threading.Event())
    assert tracked_children[0].poll() is not None
    assert tracked_children[0].stdout.closed and tracked_children[0].stderr.closed


@pytest.mark.parametrize("timeout", [10**20, 10**400], ids=["platform-range", "float-overflow"])
def test_huge_timeout_public_helper_roundtrip(helper, tracked_children, timeout):
    result = admin.execute(helper, [sys.executable, "-I", "-c", "print('wire huge timeout')"],
                           str(helper), timeout)
    assert result["returncode"] == 0
    assert result["stdout"] == "wire huge timeout" + os.linesep
    assert not result["timed_out"] and not result["revoked"]
    assert admin.status(helper)["status"] == "ready"


@pytest.mark.parametrize("timeout", [0, 10**20, 10**400], ids=["unlimited", "platform-range", "float-overflow"])
def test_response_polling_does_not_cap_command_lifetime(helper, monkeypatch, timeout):
    # Force multiple real socket polls before the ordinary scratch child exits.
    monkeypatch.setattr(admin, "IO_TIMEOUT", 0.03)
    result = admin.execute(helper, [sys.executable, "-I", "-c",
                           "import time; time.sleep(0.2); print('after polls')"], str(helper), timeout)
    assert result["returncode"] == 0
    assert result["stdout"] == "after polls" + os.linesep
    assert not result["timed_out"]


@pytest.mark.parametrize("deadline_ns", [80_000_000, 10**400 * 1_000_000_000],
                         ids=["ordinary", "huge"])
def test_socket_polls_keep_original_deadline(monkeypatch, deadline_ns):
    ticks = iter([deadline_ns - 80_000_000, deadline_ns - 40_000_000, deadline_ns])
    monkeypatch.setattr(admin, "time", SimpleNamespace(monotonic_ns=lambda: next(ticks)))
    monkeypatch.setattr(admin, "IO_TIMEOUT", 0.02)
    waits = []

    def receive(size):
        raise socket.timeout("poll elapsed")

    connection = SimpleNamespace(settimeout=waits.append, recv=receive)
    with pytest.raises(admin.AdminError, match="deadline exceeded"):
        admin._line(connection, 1024, None, deadline_ns=deadline_ns)
    assert waits == [0.02, 0.02]


def test_nonadmin_and_alternate_identity_rejected(tmp_path):
    with pytest.raises(admin.AdminError, match="elevated"):
        admin._serve(tmp_path, "sid", "id", elevation_detector=lambda: False)
    with pytest.raises(admin.AdminError, match="SID"):
        admin._serve(tmp_path, "sid", "id", elevation_detector=lambda: True,
                     identity_detector=lambda: "different")
    assert not (tmp_path / "admin").exists()


def test_cli_has_no_test_bypass(tmp_path, monkeypatch):
    monkeypatch.setattr(admin, "_serve", lambda *a, **k: (_ for _ in ()).throw(admin.AdminError("not elevated")))
    assert admin.main(["--serve", "--state-dir", str(tmp_path), "--expected-sid", "sid",
                       "--launch-id", "id"]) == 1
    with pytest.raises(SystemExit):
        admin.main(["--serve", "--state-dir", str(tmp_path), "--test-elevated"])


def test_start_quoting_spaces_and_apostrophe(tmp_path, monkeypatch):
    captured = []
    monkeypatch.setattr(admin.sys, "executable", "C:\\Program Files\\Python's\\python.exe")
    monkeypatch.setattr(admin.subprocess, "run", lambda *a, **k: captured.append((a, k)))
    path = tmp_path / "a b's"
    admin._launch(path, "S-1-5-123", "abc")
    args = captured[0][0][0]
    script = base64.b64decode(args[-1]).decode("utf-16le")
    assert "Start-Process -Verb RunAs" in script
    assert "'C:\\Program Files\\Python''s\\python.exe'" in script
    assert '"' + str(path).replace("'", "''") + '"' in script
    assert "-I -m ballz2thewall.admin --serve" in script
    assert captured[0][1]["check"] is True


def test_cancellation_clears_only_own_pending(tmp_path, monkeypatch):
    activation(tmp_path)
    monkeypatch.setattr(admin, "WINDOWS", True)
    monkeypatch.setattr(admin, "_identity", lambda: "test-sid")
    def cancelled(*args):
        raise subprocess.CalledProcessError(1, "mock approval")
    monkeypatch.setattr(admin, "_launch", cancelled)
    assert "cancelled" in admin.start(tmp_path)["error"]
    assert not (tmp_path / "admin/pending.json").exists()


def test_launch_timeout_preserves_pending(tmp_path, monkeypatch):
    activation(tmp_path)
    monkeypatch.setattr(admin, "WINDOWS", True)
    monkeypatch.setattr(admin, "_identity", lambda: "test-sid")
    def expired(*args):
        raise subprocess.TimeoutExpired("mock approval", 120)
    monkeypatch.setattr(admin, "_launch", expired)
    assert "preserved" in admin.start(tmp_path)["error"]
    before = (tmp_path / "admin/pending.json").read_bytes()
    assert "already pending" in admin.start(tmp_path)["error"]
    assert (tmp_path / "admin/pending.json").read_bytes() == before
    assert admin.stop(tmp_path)["status"] == "off"


def test_duplicate_and_stale_state_preserved(helper, monkeypatch):
    monkeypatch.setattr(admin, "WINDOWS", True)
    monkeypatch.setattr(admin, "_identity", lambda: "test-sid")
    monkeypatch.setattr(admin, "_process_exited", lambda pid: False)
    monkeypatch.setattr(admin, "_launch", lambda *a: pytest.fail("duplicate approval"))
    before = (helper / "admin/endpoint.json").read_bytes()
    assert admin.start(helper)["status"] == "ready"
    assert (helper / "admin/endpoint.json").read_bytes() == before


def test_stale_endpoint_is_not_deleted(tmp_path):
    store = reservation(tmp_path)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    endpoint = {"port": port, "token": "x" * 64}
    admin._save(store.root / "endpoint.json", endpoint)
    assert admin.status(tmp_path)["status"] == "unavailable"
    assert admin.stop(tmp_path)["status"] == "unavailable"
    assert json.loads((store.root / "endpoint.json").read_text()) == endpoint


def test_revoked_reservation_cannot_register(tmp_path):
    reservation(tmp_path)
    admin.stop(tmp_path)
    with pytest.raises(admin.AdminError, match="reservation"):
        admin._serve(tmp_path, "test-sid", "test-launch", elevation_detector=lambda: True,
                     identity_detector=lambda: "test-sid")
    assert admin._endpoint(tmp_path) is None


def test_enable_disable_wrappers(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(admin, "start", lambda state: calls.append(("start", state)) or {"status": "ready"})
    monkeypatch.setattr(admin, "stop", lambda state: calls.append(("stop", state)) or {"status": "off"})
    assert admin.enable(tmp_path) == {"status": "ready"}
    assert admin.disable(tmp_path) == {"status": "off"}
    assert calls == [("start", tmp_path), ("stop", tmp_path)]


@pytest.mark.parametrize("changes", [{"phase": "off"}, {"phase": "enabling"}, {"phase": "stopping"},
                                    {"machine_access": False}, {"machine_access": 1}])
def test_start_requires_machine_activation(tmp_path, monkeypatch, changes):
    activation(tmp_path, **changes)
    monkeypatch.setattr(admin, "WINDOWS", True)
    monkeypatch.setattr(admin, "_identity", lambda: "test-sid")
    monkeypatch.setattr(admin, "_launch", lambda *a: pytest.fail("approval while machine access denied"))
    result = admin.start(tmp_path)
    assert result["status"] == "unavailable"
    assert "machine" in result["error"].lower()
    assert not (tmp_path / "admin/pending.json").exists()


@pytest.mark.parametrize("changes", [{"phase": "off"}, {"phase": "stopping"}, {"machine_access": False},
                                    {"id": "d" * 32}])
def test_delayed_approval_cannot_register_after_activation_change(tmp_path, changes):
    reservation(tmp_path)
    activation(tmp_path, **changes)
    with pytest.raises(admin.AdminError, match="machine|activation"):
        admin._serve(tmp_path, "test-sid", "test-launch", elevation_detector=lambda: True,
                     identity_detector=lambda: "test-sid")
    assert admin._endpoint(tmp_path) is None


def test_endpoint_is_bound_to_reserved_activation(helper):
    assert admin._endpoint(helper)["activation_id"] == Activation(helper).status()["id"]


@pytest.mark.parametrize("changes", [{"phase": "off"}, {"phase": "stopping"}, {"machine_access": False},
                                    {"id": "d" * 32}])
def test_client_rejects_new_commands_after_activation_change(helper, monkeypatch, changes):
    activation(helper, **changes)
    monkeypatch.setattr(admin, "_request", lambda *a, **k: pytest.fail("forwarded revoked command"))
    with pytest.raises(admin.AdminError, match="machine|activation|off"):
        admin.execute(helper, [sys.executable], str(helper))
    monkeypatch.undo()


@pytest.mark.parametrize("identity", ["d" * 32, None, "a", 1])
def test_server_rejects_stale_or_invalid_request_identity(helper, identity):
    endpoint = admin._endpoint(helper)
    payload = {"op": "execute", "argv": [sys.executable], "cwd": str(helper),
               "timeout": 1, "activation_id": identity}
    with pytest.raises(admin.AdminError, match="activation"):
        admin._request(endpoint, payload)
    assert admin.status(helper)["status"] == "ready"


@pytest.mark.parametrize("changes", [{"phase": "off"}, {"phase": "stopping"}, {"machine_access": False},
                                    {"id": "d" * 32}])
def test_watchdog_revokes_running_child_without_stop(helper, changes):
    marker = helper / "running"
    code = f"import pathlib,time; pathlib.Path({str(marker)!r}).write_text('started'); time.sleep(20)"
    results, errors = [], []

    def run():
        try:
            results.append(admin.execute(helper, [sys.executable, "-c", code], str(helper), 0))
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 3
    while not marker.exists():
        assert not errors
        assert time.monotonic() < deadline
        time.sleep(0.01)
    started = time.monotonic()
    activation(helper, **changes)
    thread.join(3)
    assert not thread.is_alive()
    assert not errors
    assert results[0]["revoked"] is True
    assert results[0]["returncode"] != 0
    assert not results[0].get("descendants_terminated", False)
    assert time.monotonic() - started < 3
    deadline = time.monotonic() + 2
    while admin._endpoint(helper) is not None:
        assert time.monotonic() < deadline
        time.sleep(0.01)


@pytest.mark.parametrize("changes", [{"phase": "off"}, {"phase": "stopping"}, {"machine_access": False},
                                    {"id": "d" * 32}])
def test_server_checks_gate_even_when_client_is_bypassed(helper, monkeypatch, changes):
    endpoint = admin._endpoint(helper)
    assert endpoint is not None
    waiting = threading.Event()
    original_line = admin._line

    def read_request(sock, limit, deadline, **kwargs):
        if limit == admin.MAX_REQUEST:
            waiting.set()
        return original_line(sock, limit, deadline, **kwargs)

    monkeypatch.setattr(admin, "_line", read_request)
    monkeypatch.setattr(admin.subprocess, "Popen", lambda *a, **k: pytest.fail("spawned after OFF"))
    with socket.create_connection(("127.0.0.1", endpoint["port"]), 2) as connection:
        assert waiting.wait(2)
        activation(helper, **changes)
        payload = {"op": "execute", "argv": [sys.executable], "cwd": str(helper), "timeout": 1,
                   "activation_id": endpoint["activation_id"], "token": endpoint["token"]}
        connection.sendall((json.dumps(payload) + "\n").encode())
        response = original_line(connection, admin.MAX_RESPONSE, time.monotonic() + 3)
    assert any(word in response["error"].lower() for word in ("machine", "activation", "revoked"))


def test_disable_does_not_acquire_controller_lock(helper):
    with admin.Store(Activation(helper).root).lock():
        activation(helper, phase="stopping")
        assert admin.disable(helper)["status"] == "off"


@pytest.mark.parametrize("damage", ["missing", "invalid", "legacy"])
def test_watchdog_fails_closed_on_unreadable_or_legacy_activation(helper, damage):
    controller = Activation(helper)
    if damage == "missing":
        controller.path.unlink()
    elif damage == "invalid":
        admin.atomic_write(controller.path, b"{broken json")
    else:
        record = controller.status()
        del record["machine_access"]
        controller._save(record)
    deadline = time.monotonic() + 3
    while admin._endpoint(helper) is not None:
        assert time.monotonic() < deadline
        time.sleep(0.01)


def test_already_revoked_runner_never_spawns(tmp_path, monkeypatch):
    revoked = threading.Event()
    revoked.set()
    monkeypatch.setattr(admin.subprocess, "Popen", lambda *a, **k: pytest.fail("spawned after revocation"))
    with pytest.raises(admin.AdminError, match="revoked"):
        admin._run_command([sys.executable], str(tmp_path), 1, revoked)


@pytest.fixture
def approved_launcher(monkeypatch):
    """A same-identity threaded test helper, never a real UAC launch."""
    workers, reservations, errors = [], [], []

    def launch(state, sid, launch_id):
        reservations.append(admin._read(admin._store(state).root / "pending.json"))

        def run():
            try:
                admin._serve(state, sid, launch_id, elevation_detector=lambda: True,
                             identity_detector=lambda: sid)
            except Exception as exc:
                errors.append(exc)

        thread = threading.Thread(target=run, daemon=True)
        workers.append((state, thread))
        thread.start()

    monkeypatch.setattr(admin, "WINDOWS", True)
    monkeypatch.setattr(admin, "_identity", lambda: "test-sid")
    monkeypatch.setattr(admin, "_launch", launch)
    monkeypatch.setattr(admin, "_process_exited", lambda pid: False)
    yield reservations
    for state, thread in workers:
        admin.stop(state)
        thread.join(4)
        assert not thread.is_alive()
    assert not errors


def test_start_binds_pending_and_endpoint_to_activation(tmp_path, approved_launcher):
    record = activation(tmp_path)
    with admin.Store(Activation(tmp_path).root).lock():
        assert admin.enable(tmp_path)["status"] == "ready"
    endpoint = admin._endpoint(tmp_path)
    assert endpoint is not None
    assert endpoint["activation_id"] == record["id"]
    assert approved_launcher == [{"sid": "test-sid", "launch_id": endpoint["launch_id"],
                                  "activation_id": record["id"]}]


@pytest.fixture
def stale_endpoint(tmp_path):
    activation(tmp_path)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    endpoint = {"port": port, "token": "x" * 64, "pid": 12345, "sid": "test-sid",
                "launch_id": "old-launch", "activation_id": "a" * 32}
    store = admin._store(tmp_path)
    with store.lock():
        admin._save(store.root / "endpoint.json", endpoint)
    return tmp_path, endpoint


def test_start_recovers_verified_dead_endpoint(stale_endpoint, approved_launcher, monkeypatch):
    state, before = stale_endpoint
    monkeypatch.setattr(admin, "_process_exited", lambda pid: pid == before["pid"])
    assert admin.enable(state)["status"] == "ready"
    after = admin._endpoint(state)
    assert after is not None
    assert after["token"] != before["token"]
    assert len(approved_launcher) == 1
    # The test helper is alive: leave its teardown to the authenticated stop path.
    monkeypatch.setattr(admin, "_process_exited", lambda pid: False)


def test_stop_recovers_verified_dead_endpoint(stale_endpoint, monkeypatch):
    state, _ = stale_endpoint
    monkeypatch.setattr(admin, "_process_exited", lambda pid: True)
    assert admin.disable(state) == {"status": "off", "elevated": False, "descendants_terminated": False}
    assert admin._endpoint(state) is None


def test_closed_port_with_live_or_unknown_process_is_preserved(stale_endpoint, approved_launcher):
    state, endpoint = stale_endpoint
    assert admin.enable(state)["status"] == "unavailable"
    assert admin._endpoint(state) == endpoint
    assert approved_launcher == []


def test_live_port_with_dead_pid_is_preserved(stale_endpoint, monkeypatch):
    state, endpoint = stale_endpoint
    monkeypatch.setattr(admin, "_process_exited", lambda pid: True)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        endpoint["port"] = listener.getsockname()[1]
        admin._save(admin._store(state).root / "endpoint.json", endpoint)
        assert admin._remove_stale_endpoint(state, endpoint) is False
    assert admin._endpoint(state) == endpoint


@pytest.mark.parametrize("failure", [TimeoutError(), PermissionError()])
def test_uncertain_port_probe_preserves_endpoint(stale_endpoint, monkeypatch, failure):
    state, endpoint = stale_endpoint
    monkeypatch.setattr(admin, "_process_exited", lambda pid: True)

    def unavailable(*a, **k):
        raise failure

    monkeypatch.setattr(admin.socket, "create_connection", unavailable)
    assert admin._remove_stale_endpoint(state, endpoint) is False
    assert admin._endpoint(state) == endpoint


def test_stale_recovery_does_not_delete_replacement(stale_endpoint, monkeypatch):
    state, endpoint = stale_endpoint
    replacement = {**endpoint, "token": "y" * 64}
    monkeypatch.setattr(admin, "_process_exited", lambda pid: True)

    def replaced(*a, **k):
        admin._save(admin._store(state).root / "endpoint.json", replacement)
        raise ConnectionRefusedError()

    monkeypatch.setattr(admin.socket, "create_connection", replaced)
    assert admin._remove_stale_endpoint(state, endpoint) is False
    assert admin._endpoint(state) == replacement


@pytest.mark.parametrize("pid", [None, True, 0, -1, "123", 0x100000000])
def test_invalid_process_identity_is_not_recoverable(pid, monkeypatch):
    monkeypatch.setattr(admin.os, "kill", lambda *a: pytest.fail("invalid PID probe"))
    assert admin._process_exited(pid) is False


@pytest.mark.parametrize("outcome,expected", [(None, False), (ProcessLookupError(), True),
                                           (PermissionError(), False)])
def test_posix_process_probe_is_read_only(monkeypatch, outcome, expected):
    monkeypatch.setattr(admin, "WINDOWS", False)
    calls = []

    def probe(pid, signal):
        calls.append((pid, signal))
        if outcome is not None:
            raise outcome

    monkeypatch.setattr(admin.os, "kill", probe)
    assert admin._process_exited(123) is expected
    assert calls == [(123, 0)]


@pytest.mark.parametrize("handle,wait,error,expected", [(123, 0, 0, True), (123, 258, 0, False),
                        (123, 0xFFFFFFFF, 0, False), (0, 0, 87, True), (0, 0, 5, False)])
def test_windows_process_probe_never_requests_termination(monkeypatch, handle, wait, error, expected):
    calls = []

    def open_process(access, inherit, pid):
        calls.append(("open", access, inherit, pid))
        return handle

    def wait_process(value, timeout):
        calls.append(("wait", value, timeout))
        return wait

    def close(value):
        calls.append(("close", value))
        return True

    kernel = SimpleNamespace(OpenProcess=open_process, WaitForSingleObject=wait_process, CloseHandle=close)
    monkeypatch.setattr(admin, "WINDOWS", True)
    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **k: kernel, raising=False)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: error, raising=False)
    monkeypatch.setattr(admin.os, "kill", lambda *a: pytest.fail("os.kill must not run on Windows"))
    assert admin._process_exited(456) is expected
    assert calls == [("open", 0x00100000, False, 456)] + (
        [("wait", handle, 0), ("close", handle)] if handle else [])
