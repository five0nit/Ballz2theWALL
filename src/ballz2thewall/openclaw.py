"""Local OpenClaw JSON5 policy plans and recoverable two-file transactions.

The bundle is a write-ahead journal, not an atomic filesystem snapshot. It keeps
native Store receipts in a private directory and preflights *both* files before
restoring either. Comments normalize on ON; OFF restores exact original bytes.
"""
from __future__ import annotations

import json
import math
import re
import uuid
from pathlib import Path

import json5

from .config import Plan, checked_path, encode, parse, set_dotted
from .store import Store, atomic_write, digest, read_optional

_NAMES = ("openclaw.json", "exec-approvals.json")
_STATUSES = {"prepared", "applied", "rolling_back", "rolled_back"}
_POLICY = {
    "tools.profile": "full",
    "tools.allow": ["*"],
    "tools.deny": [],
    "tools.exec.host": "gateway",
    "tools.exec.mode": "full",
    "tools.exec.strictInlineEval": False,
    "tools.fs.workspaceOnly": False,
    "tools.exec.applyPatch.workspaceOnly": False,
}
_APPROVALS = {"security": "full", "ask": "off", "askFallback": "full"}


def _invalid_constant(_value):
    raise ValueError("Nonfinite JSON5 constant")


def _finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Nonfinite JSON5 number")
    if isinstance(value, dict):
        for item in value.values():
            _finite(item)
    elif isinstance(value, list):
        for item in value:
            _finite(item)


def parse_config(data: bytes) -> dict:
    """Parse JSON5 without duplicates/nonfinite numbers or diagnostic leakage."""
    try:
        text = data.decode("utf-8")
        result = json5.loads(text, allow_duplicate_keys=False, parse_constant=_invalid_constant) if text.strip() else {}
        if not isinstance(result, dict):
            raise ValueError("Expected mapping")
        _finite(result)
        return result
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise ValueError("Invalid OpenClaw JSON5: expected UTF-8 object without duplicate keys or nonfinite numbers") from None


def _section(data: dict, name: str, label: str) -> dict:
    value = data.setdefault(name, {})
    if not isinstance(value, dict):
        raise ValueError(f"Invalid OpenClaw {label}: expected an object")
    return value


def _unsupported(value):
    if isinstance(value, dict):
        if "$include" in value:
            raise ValueError("OpenClaw $include is unsupported; use a self-contained native config")
        gateway = value.get("gateway")
        if isinstance(gateway, dict) and gateway.get("mode") == "remote":
            raise ValueError("OpenClaw remote gateway is unsupported; only a local gateway can be managed")
        tools = value.get("tools")
        if isinstance(tools, dict):
            execution = tools.get("exec")
            if isinstance(execution, dict) and execution.get("host") == "node":
                raise ValueError("OpenClaw node execution host is unsupported; only a local gateway can be managed")
            if "byProvider" in tools and (not isinstance(tools["byProvider"], dict) or tools["byProvider"]):
                raise ValueError("OpenClaw tools.byProvider overrides are unsupported")
        for item in value.values():
            _unsupported(item)
    elif isinstance(value, list):
        for item in value:
            _unsupported(item)


def _patch(data: dict, values: dict) -> bool:
    changed = False
    if "tools.exec.mode" in values:
        execution = data.get("tools", {}).get("exec", {}) if isinstance(data.get("tools", {}), dict) else {}
        if isinstance(execution, dict):
            for legacy in ("security", "ask"):
                if legacy in execution:
                    del execution[legacy]
                    changed = True
    for name, value in values.items():
        changed = set_dotted(data, name, value) or changed
    return changed


def make_plans(home: Path) -> list[Plan]:
    """Plan both local native files before any write; never resolve ENV refs."""
    targets = [checked_path(home / name).resolve() for name in _NAMES]
    before = [read_optional(target) for target in targets]
    config = parse_config(before[0] or b"{}")
    approvals = parse_config(before[1] or b"{}")
    _unsupported(config)
    _unsupported(approvals)
    agents = _section(config, "agents", "agents")
    entries = agents.get("list", [])
    if not isinstance(entries, list):
        raise ValueError("Invalid OpenClaw agents.list: expected an array")
    seen = set()
    for entry in entries:
        if (not isinstance(entry, dict) or not isinstance(entry.get("id"), str)
                or not entry["id"].strip() or entry["id"] in seen):
            raise ValueError("Invalid OpenClaw agent: expected objects with unique nonempty string IDs")
        if entry.get("runtime") is not None:
            raise ValueError("OpenClaw explicit per-agent runtime overrides are unsupported")
        seen.add(entry["id"])
    values = {**_POLICY, "agents.defaults.sandbox.mode": "off"}
    changed = _patch(config, values)
    # set_dotted detaches intermediate mappings, including agents/list.
    entries = config["agents"].get("list", [])
    for index, entry in enumerate(entries):
        agent_values = {**_POLICY, "sandbox.mode": "off"}
        changed = _patch(entry, agent_values) or changed
        values.update({f"agents.list[{index}].{key}": value for key, value in agent_values.items()})
    if before[1] is None:
        approvals["version"] = 1
    if type(approvals.get("version")) is not int or approvals["version"] != 1:
        raise ValueError("Invalid OpenClaw exec-approvals version: expected integer 1")
    approval_values = {f"defaults.{key}": value for key, value in _APPROVALS.items()}
    approvals_changed = _patch(approvals, approval_values)
    approval_agents = _section(approvals, "agents", "approval agents")
    if "*" not in approval_agents:
        approval_agents["*"] = {}
        approvals_changed = True
    for index, entry in enumerate(approval_agents.values()):
        if not isinstance(entry, dict):
            raise ValueError("Invalid OpenClaw approval agent: expected an object")
        approvals_changed = _patch(entry, _APPROVALS) or approvals_changed
        approval_values.update({f"agents[{index}].{key}": value for key, value in _APPROVALS.items()})
    return [
        Plan(targets[0], before[0], encode(config, _NAMES[0]) if changed or before[0] is None else before[0],
             values, "openclaw"),
        Plan(targets[1], before[1], encode(approvals, _NAMES[1]) if approvals_changed or before[1] is None else before[1],
             approval_values, "openclaw"),
    ]


def _valid_id(value) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{32}", value) is not None


def _valid_hash(value) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _path(value) -> Path:
    if not isinstance(value, str) or "\x00" in value or not Path(value).is_absolute():
        raise ValueError("Invalid OpenClaw bundle path")
    path = Path(value)
    if str(path.resolve()) != value:
        raise ValueError("Invalid OpenClaw bundle path")
    return path


class OpenClawStore:
    """A durable journal coordinating two unmodified single-file Stores."""

    def __init__(self, root: Path):
        self.root = root.expanduser().absolute()

    def _receipt(self, receipt_id: str) -> Path:
        if not _valid_id(receipt_id):
            raise ValueError("Receipt ID must be 32 lowercase hexadecimal characters")
        return checked_path(self.root / f"{receipt_id}.bundle.json")

    def _save(self, record: dict) -> None:
        atomic_write(self._receipt(record["id"]), (json.dumps(record, indent=2) + "\n").encode())

    def _load(self, receipt_id: str) -> dict:
        path = self._receipt(receipt_id)
        try:
            raw = read_optional(path)
            record = dict(parse(raw or b"", "receipt.json"))
        except (OSError, ValueError):
            raise ValueError("OpenClaw bundle receipt not found or invalid") from None
        if (set(record) != {"schema", "adapter", "id", "home", "status", "files"}
                or type(record["schema"]) is not int or record["schema"] != 1
                or record["adapter"] != "openclaw" or record["id"] != receipt_id
                or not isinstance(record["status"], str) or record["status"] not in _STATUSES
                or not isinstance(record["files"], list) or len(record["files"]) != 2):
            raise ValueError("Invalid OpenClaw bundle receipt")
        home = _path(record["home"])
        for entry, name in zip(record["files"], _NAMES, strict=True):
            if (not isinstance(entry, dict)
                    or set(entry) != {"name", "target", "before_sha256", "after_sha256", "receipt_id"}
                    or entry["name"] != name or entry["target"] != str(home / name)
                    or not _valid_hash(entry["after_sha256"])
                    or (entry["before_sha256"] is not None and not _valid_hash(entry["before_sha256"]))
                    or (entry["receipt_id"] is not None and not _valid_id(entry["receipt_id"]))):
                raise ValueError("Invalid OpenClaw bundle file record")
            checked_path(_path(entry["target"]))
        return record

    def _children(self, record: dict) -> Store:
        return Store(self.root / f'{record["id"]}.files')

    def _discover(self, record: dict) -> Store:
        """Bind orphan prepared receipts after a child write/return interruption."""
        child = self._children(record)
        found = {}
        with child.lock():
            for path in child.root.glob("*.json"):
                if not _valid_id(path.stem):
                    raise ValueError("Invalid OpenClaw child receipt name")
                try:
                    metadata = dict(parse(read_optional(path) or b"", "receipt.json"))
                except (OSError, ValueError):
                    raise ValueError("Invalid OpenClaw child receipt") from None
                expected = next((entry for entry in record["files"] if entry["target"] == metadata.get("target")), None)
                if (expected is None or metadata.get("id") != path.stem
                        or type(metadata.get("schema")) is not int or metadata["schema"] != 1
                        or metadata.get("adapter") != "openclaw"
                        or not isinstance(metadata.get("status"), str) or metadata["status"] not in _STATUSES
                        or "before_sha256" not in metadata
                        or metadata["before_sha256"] != expected["before_sha256"]
                        or metadata.get("after_sha256") != expected["after_sha256"]
                        or type(metadata.get("before_mode")) is not int
                        or not 0 <= metadata["before_mode"] <= 0o7777
                        or metadata["target"] in found
                        or expected["before_sha256"] == expected["after_sha256"]):
                    raise ValueError("Invalid OpenClaw child receipt scope")
                if (metadata["status"] == "rolled_back"
                        and digest(read_optional(Path(metadata["target"]))) != expected["before_sha256"]):
                    raise ValueError("OpenClaw child receipt/config drift detected")
                found[metadata["target"]] = path.stem
            for entry in record["files"]:
                discovered = found.get(entry["target"])
                if entry["receipt_id"] is not None and entry["receipt_id"] != discovered:
                    raise ValueError("OpenClaw child receipt missing or mismatched")
                entry["receipt_id"] = discovered
        return child

    def _preflight_restore(self, record: dict, child: Store) -> None:
        # Validate ALL backup bytes and current targets before calling rollback.
        for entry in record["files"]:
            current = digest(read_optional(Path(entry["target"])))
            allowed = {entry["before_sha256"], entry["after_sha256"]}
            if record["status"] == "rolled_back":
                allowed = {entry["before_sha256"]}
            if current not in allowed:
                raise ValueError("OpenClaw config drift detected; rollback blocked")
            receipt_id = entry["receipt_id"]
            if receipt_id is None:
                if current != entry["before_sha256"]:
                    raise ValueError("OpenClaw child receipt missing for modified config")
                continue
            if entry["before_sha256"] is not None:
                backup = read_optional(child.root / f"{receipt_id}.before")
                if backup is None or digest(backup) != entry["before_sha256"]:
                    raise ValueError("Backup missing or corrupted; rollback blocked")

    def _rollback(self, record: dict) -> dict:
        child = self._discover(record)
        self._preflight_restore(record, child)
        if record["status"] == "rolled_back":
            return {"status": "already_rolled_back", "receipt_id": record["id"]}
        record["status"] = "rolling_back"
        self._save(record)
        for entry in reversed(record["files"]):
            # Recheck the complete bundle before each restore as native editors
            # do not participate in the controller's advisory lock.
            self._preflight_restore(record, child)
            if entry["receipt_id"] is not None:
                child.rollback(entry["receipt_id"])
        if any(digest(read_optional(Path(entry["target"]))) != entry["before_sha256"] for entry in record["files"]):
            raise ValueError("OpenClaw rollback verification failed; retry using the bundle receipt")
        record["status"] = "rolled_back"
        self._save(record)
        return {"status": "rolled_back", "receipt_id": record["id"]}

    def apply(self, plans: list[Plan]) -> dict:
        if (not isinstance(plans, list) or len(plans) != 2
                or any(not isinstance(plan, Plan) or plan.adapter != "openclaw"
                       or not isinstance(plan.target, Path) or not isinstance(plan.after, bytes)
                       or (plan.before is not None and not isinstance(plan.before, bytes)) for plan in plans)):
            raise ValueError("OpenClaw requires exactly two native file plans")
        home = plans[0].target.parent
        for plan, name in zip(plans, _NAMES, strict=True):
            if plan.target != home / name or checked_path(plan.target) != _path(str(plan.target)):
                raise ValueError("Invalid OpenClaw plan target scope")
        with Store(self.root).lock():
            if any(read_optional(plan.target) != plan.before for plan in plans):
                raise ValueError("Config changed after planning; regenerate both plans")
            if all(plan.before == plan.after for plan in plans):
                return {"status": "unchanged", "receipt_id": None}
            record = {"schema": 1, "adapter": "openclaw", "id": uuid.uuid4().hex,
                      "home": str(home), "status": "prepared", "files": [
                          {"name": plan.target.name, "target": str(plan.target),
                           "before_sha256": digest(plan.before), "after_sha256": digest(plan.after),
                           "receipt_id": None} for plan in plans]}
            # Persist both intended hashes and target names BEFORE any native write.
            self._save(record)
            child = self._children(record)
            try:
                for entry, plan in zip(record["files"], plans, strict=True):
                    result = child.apply(plan)
                    entry["receipt_id"] = result["receipt_id"]
                    self._save(record)
                if any(digest(read_optional(plan.target)) != digest(plan.after) for plan in plans):
                    raise ValueError("OpenClaw apply verification failed")
                record["status"] = "applied"
                self._save(record)
            except Exception:
                # A child can write then throw before returning its ID. Reload
                # the durable journal and discover those receipts before recovery.
                try:
                    self._rollback(self._load(record["id"]))
                    outcome = "original files restored"
                except Exception:
                    outcome = "recovery pending; inspect or retry rollback"
                raise ValueError(f'OpenClaw apply failed; {outcome}; bundle receipt {record["id"]}') from None
            return {"status": "applied", "receipt_id": record["id"], "receipt": str(self._receipt(record["id"]))}

    def rollback(self, receipt_id: str) -> dict:
        self._receipt(receipt_id)
        with Store(self.root).lock():
            return self._rollback(self._load(receipt_id))

    def validate(self, receipt_id: str, home: Path) -> dict:
        """Validate activation scope and both after-hashes without exposing data."""
        self._receipt(receipt_id)
        with Store(self.root).lock():
            record = self._load(receipt_id)
            expected_home = checked_path(home / _NAMES[0]).resolve().parent
            if record["home"] != str(expected_home) or record["status"] != "applied":
                raise ValueError("Invalid OpenClaw activation bundle scope or status")
            self._discover(record)
            for entry in record["files"]:
                if (entry["before_sha256"] != entry["after_sha256"] and entry["receipt_id"] is None):
                    raise ValueError("OpenClaw activation child receipt missing")
                if digest(read_optional(Path(entry["target"]))) != entry["after_sha256"]:
                    raise ValueError("OpenClaw activation config drift detected")
            return {"status": "valid", "receipt_id": receipt_id, "home": str(expected_home)}
