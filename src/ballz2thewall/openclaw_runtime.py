"""OpenClaw native probes and local embedded launch; no gateway lifecycle control."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from .adapters import get_adapter


def _environment(home: Path) -> dict[str, str]:
    return {**os.environ, **get_adapter("openclaw").environment(home), "NO_COLOR": "1"}


def inspect_native(adapter, home: Path | None = None) -> dict:
    exe = shutil.which(adapter.executable)
    result = {"adapter": adapter.name, "executable": exe, "version": None,
              "tested_version": adapter.tested_version, "native_flag": adapter.flag,
              "flag_supported": False, "status": "missing", "auth": "not_probed"}
    if home is not None and home.name != ".openclaw":
        return {**result, "status": "unsupported",
                "detail": "This alpha requires a .openclaw home; named/custom state layouts use a shared native approval path"}
    if os.name == "nt":
        return {**result, "status": "unsupported", "detail": "Use OpenClaw and Ballz together inside WSL2"}
    if not exe:
        return result
    # Probe only an empty temporary profile, never the user's active gateway home.
    with tempfile.TemporaryDirectory(prefix="ballz-openclaw-probe-") as temporary:
        home = Path(temporary) / ".openclaw"
        env = _environment(home)
        env.update(HOME=temporary, OPENCLAW_HOME=temporary)
        try:
            version = subprocess.run([exe, "--version"], capture_output=True, text=True,
                                     env=env, timeout=25, check=False)
            help_run = subprocess.run([exe, "agent", "--help"], capture_output=True, text=True,
                                      env=env, timeout=25, check=False)
            policy = subprocess.run([exe, "exec-policy", "show", "--help"], capture_output=True,
                                    text=True, env=env, timeout=25, check=False)
            match = re.search(r"(?<![\w.])v?(\d+\.\d+\.\d+)\b", version.stdout)
            result["version"] = match.group(1) if match else None
            result["flag_supported"] = (help_run.returncode == 0 and policy.returncode == 0
                                        and "--local" in help_run.stdout and "--message" in help_run.stdout
                                        and "--session-id" in help_run.stdout and "--json" in policy.stdout)
            result["version_match"] = result["version"] == adapter.tested_version
            result["status"] = "ready" if result["flag_supported"] and version.returncode == 0 else "unsupported"
        except (OSError, subprocess.SubprocessError):
            result["status"] = "probe_failed"
    return result


def verify_native(home: Path, executable: str) -> dict:
    """Native schema + effective-policy readback. Never return native config/logs."""
    env = _environment(home)
    try:
        valid = subprocess.run([executable, "config", "validate", "--json"], env=env,
                               capture_output=True, text=True, timeout=45, check=False)
        if valid.returncode or json.loads(valid.stdout).get("valid") is not True:
            raise ValueError("OpenClaw native config validation failed; original files will be restored")
        policy = subprocess.run([executable, "exec-policy", "show", "--json"], env=env,
                                capture_output=True, text=True, timeout=45, check=False)
        if policy.returncode:
            raise ValueError("OpenClaw effective policy probe failed")
        data = json.loads(policy.stdout)
        if (Path(data["configPath"]).resolve() != (home / "openclaw.json").resolve()
                or Path(data["approvalsPath"]).resolve() != (home / "exec-approvals.json").resolve()):
            raise ValueError("OpenClaw effective policy resolved a different home")
        scopes = data["effectivePolicy"]["scopes"]
        if not isinstance(scopes, list) or not scopes:
            raise ValueError("OpenClaw effective policy has no scopes")
        for scope in scopes:
            if (scope["host"]["requested"] != "gateway" or scope["security"]["effective"] != "full"
                    or scope["ask"]["effective"] != "off"
                    or scope.get("runtimeApprovalsSource", "local-file") != "local-file"):
                raise ValueError("OpenClaw effective policy is not local/full/off")
        return {"native_config_valid": True, "effective_scopes": len(scopes),
                "host": "gateway", "security": "full", "ask": "off"}
    except (KeyError, TypeError, AttributeError, json.JSONDecodeError, OSError, subprocess.SubprocessError):
        raise ValueError("OpenClaw native validation failed or returned an unsupported policy schema") from None


def apply_verified(store, plans, home: Path, executable: str) -> dict:
    result = store.apply(plans)
    try:
        verified = verify_native(home, executable)
    except Exception:
        receipt_id = result.get("receipt_id")
        if receipt_id:
            try:
                store.rollback(receipt_id)
            except Exception:
                raise ValueError(f"OpenClaw native validation failed; recovery pending for receipt {receipt_id}") from None
        raise ValueError("OpenClaw native validation failed; prior files restored or unchanged") from None
    return {**result, **verified}


def launch(argv: list[str], prompt: str | None, interactive: bool, cwd: Path, env: dict) -> int:
    """Forward terminal input to native agent --local; no model orchestration.

    OpenClaw requires --message (no stdin-prompt CLI contract). The prompt is
    consequently visible in the native process arguments, but never receipts.
    """
    session = uuid.uuid4().hex
    if interactive:
        print("OpenClaw local session. Enter a message; /exit ends this session.")
    while True:
        if interactive:
            try:
                prompt = input("You > ")
            except EOFError:
                return 0
            if prompt.strip() == "/exit":
                return 0
            if not prompt.strip():
                continue
        result = subprocess.run([*argv, "--session-id", session, "--message", prompt or ""],
                                cwd=cwd, env=env, text=True, check=False, shell=False)
        if not interactive or result.returncode:
            return result.returncode
