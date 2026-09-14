"""Single-file reversible transactions. Receipts contain hashes, never config values."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .config import Plan, checked_path, parse


def digest(data: bytes | None) -> str | None:
    return hashlib.sha256(data).hexdigest() if data is not None else None


def read_optional(path: Path) -> bytes | None:
    checked_path(path)
    return path.read_bytes() if path.exists() else None


def atomic_write(path: Path, data: bytes, mode: int = 0o600) -> None:
    checked_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".ballz-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        sync_dir(path.parent)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def sync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class Store:
    def __init__(self, root: Path):
        self.root = root.expanduser().absolute()

    @contextmanager
    def lock(self):
        if os.name != "posix":
            raise ValueError("Write/rollback currently require Linux, WSL or macOS (POSIX)")
        import fcntl
        checked_path(self.root / "lock")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.root.stat().st_uid != os.getuid():
            raise ValueError("State directory must belong to the current user")
        if stat.S_IMODE(self.root.stat().st_mode) & 0o077:
            raise ValueError("State directory must have mode 0700")
        fd = os.open(self.root / "lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _receipt(self, receipt_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", receipt_id):
            raise ValueError("Receipt ID must be 32 lowercase hexadecimal characters")
        return checked_path(self.root / f"{receipt_id}.json")

    def _save(self, record: dict) -> None:
        atomic_write(self._receipt(record["id"]), (json.dumps(record, indent=2) + "\n").encode())

    def apply(self, plan: Plan) -> dict:
        with self.lock():
            if read_optional(plan.target) != plan.before:
                raise ValueError("Config changed after planning; regenerate the plan")
            if plan.before == plan.after:
                return {"status": "unchanged", "target": str(plan.target), "receipt_id": None}
            receipt_id = uuid.uuid4().hex
            mode = stat.S_IMODE(plan.target.stat().st_mode) if plan.before is not None else 0o600
            if plan.before is not None:
                atomic_write(self.root / f"{receipt_id}.before", plan.before)
            record = {"schema": 1, "id": receipt_id, "adapter": plan.adapter,
                      "target": str(plan.target), "created_at": datetime.now(timezone.utc).isoformat(),
                      "before_sha256": digest(plan.before), "after_sha256": digest(plan.after),
                      "before_mode": mode, "status": "prepared"}
            self._save(record)
            # Recheck immediately before replacing; unrelated native editors do not take our lock.
            if read_optional(plan.target) != plan.before:
                raise ValueError("Config changed during apply; no config was written")
            atomic_write(plan.target, plan.after, mode=mode)
            if digest(read_optional(plan.target)) != record["after_sha256"]:
                raise ValueError("Config verification failed; inspect prepared receipt")
            record["status"] = "applied"
            self._save(record)
            return {"status": "applied", "target": str(plan.target), "receipt_id": receipt_id,
                    "receipt": str(self._receipt(receipt_id)), "sha256": record["after_sha256"]}

    def rollback(self, receipt_id: str) -> dict:
        with self.lock():
            receipt_path = self._receipt(receipt_id)
            try:
                record = dict(parse(receipt_path.read_bytes(), "receipt.json"))
            except (OSError, ValueError):
                raise ValueError("Receipt not found or invalid") from None
            def valid_hash(value):
                return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None

            if (type(record.get("schema")) is not int or record["schema"] != 1
                    or record.get("id") != receipt_id
                    or not isinstance(record.get("status"), str)
                    or record["status"] not in {"applied", "prepared", "rolled_back"}
                    or not isinstance(record.get("target"), str)
                    or "\x00" in record["target"] or not Path(record["target"]).is_absolute()
                    or not valid_hash(record.get("after_sha256"))
                    or "before_sha256" not in record
                    or (record["before_sha256"] is not None and not valid_hash(record["before_sha256"]))
                    or type(record.get("before_mode")) is not int
                    or not 0 <= record["before_mode"] <= 0o7777):
                raise ValueError("Invalid transaction receipt")
            target = checked_path(Path(record["target"]))
            current_hash = digest(read_optional(target))
            if record["status"] == "rolled_back":
                if current_hash != record["before_sha256"]:
                    raise ValueError("Config drifted after rollback")
                return {"status": "already_rolled_back", "target": str(target), "receipt_id": receipt_id}
            if current_hash != record["after_sha256"]:
                if record["status"] == "prepared" and current_hash == record["before_sha256"]:
                    record["status"] = "rolled_back"
                    self._save(record)
                    return {"status": "not_applied", "target": str(target), "receipt_id": receipt_id}
                raise ValueError("Config drift detected; rollback would overwrite newer edits")
            if record["before_sha256"] is None:
                target.unlink()
                sync_dir(target.parent)
            else:
                before = read_optional(self.root / f"{receipt_id}.before")
                if before is None or digest(before) != record["before_sha256"]:
                    raise ValueError("Backup missing or corrupted")
                atomic_write(target, before, mode=record["before_mode"])
            if digest(read_optional(target)) != record["before_sha256"]:
                raise ValueError("Rollback verification failed")
            record["status"] = "rolled_back"
            self._save(record)
            return {"status": "rolled_back", "target": str(target), "receipt_id": receipt_id}
