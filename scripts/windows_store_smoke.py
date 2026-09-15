#!/usr/bin/env python3
"""Native Windows Store smoke: synthetic scratch data only; retain JSON receipt."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from ballz2thewall import platform_store
from ballz2thewall.config import Plan
from ballz2thewall.store import Store, read_optional


def expect_rejected(call, fragment):
    try:
        call()
    except ValueError as exc:
        assert fragment in str(exc), str(exc)
        return
    raise AssertionError(f"Expected rejection: {fragment}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch-parent", type=Path)
    parser.add_argument("--lock-child", type=Path)
    parser.add_argument("--marker", type=Path)
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("Run with native Windows Python, not WSL Python")
    if args.lock_child:
        args.marker.with_suffix(".started").write_text("started")
        with Store(args.lock_child).lock():
            args.marker.write_text("acquired")
        return

    scratch = Path(tempfile.mkdtemp(prefix="ballz-store-smoke-", dir=args.scratch_parent))
    checks = []
    store = Store(scratch / "private-state")
    target = scratch / "synthetic-home" / "config.json"
    target.parent.mkdir()
    for before in (b'{"synthetic":"original"}\r\n', None):
        if before is None:
            target.unlink()
        else:
            target.write_bytes(before)
        after = b'{"synthetic":"changed"}\n'
        result = store.apply(Plan(target, before, after, {}, "smoke"))
        assert target.read_bytes() == after
        assert store.apply(Plan(target, after, after, {}, "smoke"))["status"] == "unchanged"
        platform_store.validate_private_directory(store.root)
        assert Store(store.root).rollback(result["receipt_id"])["status"] == "rolled_back"
        assert read_optional(target) == before
        assert store.rollback(result["receipt_id"])["status"] == "already_rolled_back"
    checks.append("apply/unchanged/rollback/restart/idempotence/exact-bytes/absence")

    result = store.apply(Plan(target, None, b"new", {}, "smoke"))
    target.write_bytes(b"newer-edit")
    expect_rejected(lambda: store.rollback(result["receipt_id"]), "drift")
    assert target.read_bytes() == b"newer-edit"
    checks.append("drift-refused-without-overwrite")

    result = store.apply(Plan(target, b"newer-edit", b"after", {}, "smoke"))
    (store.root / f'{result["receipt_id"]}.before').write_bytes(b"corrupt")
    expect_rejected(lambda: store.rollback(result["receipt_id"]), "corrupted")
    assert target.read_bytes() == b"after"
    checks.append("corrupt-backup-refused")

    marker = scratch / "child-acquired"
    child = None
    try:
        with store.lock():
            child = subprocess.Popen([sys.executable, __file__, "--lock-child", str(store.root),
                                      "--marker", str(marker)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            deadline = time.monotonic() + 10
            while not marker.with_suffix(".started").exists() and time.monotonic() < deadline:
                assert child.poll() is None, "lock child exited early"
                time.sleep(0.02)
            assert marker.with_suffix(".started").exists(), "child did not start"
            time.sleep(0.3)
            assert not marker.exists(), "child entered a lock held by parent"
        stdout, stderr = child.communicate(timeout=10)
        assert child.returncode == 0, (stdout, stderr)
        assert marker.read_text() == "acquired"
    finally:
        if child is not None and child.poll() is None:
            child.kill()
            child.communicate()
    checks.append("cross-process-mutual-exclusion-and-release")

    # New state receives a protected owner-only ACL; broad parent is unchanged.
    insecure = scratch / "insecure-state"
    insecure.mkdir()
    # Isolate the ACL rejection from elevated tokens' default Administrators owner.
    subprocess.run(["icacls.exe", str(insecure), "/setowner", "*" + platform_store.current_user_sid()],
                   check=True, capture_output=True)
    expect_rejected(lambda: platform_store.prepare_state_directory(insecure), "ACL")
    broad = scratch / "broad-state"
    platform_store.prepare_state_directory(broad)
    subprocess.run(["icacls.exe", str(broad), "/grant", "*S-1-1-0:(R)"],
                   check=True, capture_output=True)
    expect_rejected(lambda: platform_store.prepare_state_directory(broad), "another principal")
    checks.append("inherited-and-everyone-acls-refused")

    exposed = scratch / "exposed-backup-state"
    platform_store.prepare_state_directory(exposed)
    backup = exposed / "synthetic.before"
    backup.write_bytes(b"synthetic only")
    platform_store.private_file(backup)  # Establish correct owner before widening its ACL.
    subprocess.run(["icacls.exe", str(backup), "/grant", "*S-1-1-0:(R)"],
                   check=True, capture_output=True)
    def enter_exposed_store():
        with Store(exposed).lock():
            raise AssertionError("Store accepted a broadly readable backup")
    expect_rejected(enter_exposed_store, "another principal")
    checks.append("explicit-permissive-child-acl-refused")

    junction = scratch / "junction"
    subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(target.parent)],
                   check=True, capture_output=True)
    try:
        expect_rejected(lambda: platform_store.prepare_state_directory(junction / "state"), "reparse")
        expect_rejected(lambda: read_optional(junction / "config.json"), "reparse")
        expect_rejected(lambda: Store(junction).apply(Plan(target, b"after", b"bad", {}, "smoke")), "reparse")
        assert target.read_bytes() == b"after"
    finally:
        junction.rmdir()  # Remove junction, never recurse into its target.
    checks.append("junction-root-parent-and-target-refused")

    linked = scratch / "hardlink"
    os.link(target, linked)
    try:
        expect_rejected(lambda: read_optional(linked), "hard linked")
    finally:
        linked.unlink()
    checks.append("hard-linked-file-refused")
    acl = subprocess.run(["icacls.exe", str(store.root)], check=True, capture_output=True, text=True).stdout
    receipt = {"status": "passed", "platform": sys.platform, "python": sys.version,
               "executable": sys.executable, "scratch": str(scratch), "checks": checks,
               "state_acl": acl, "durability": "file fsync + same-volume MoveFileExW WRITE_THROUGH; no directory fsync"}
    output = scratch / "windows-store-receipt.json"
    output.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps({**receipt, "receipt": str(output)}, indent=2))


if __name__ == "__main__":
    main()
