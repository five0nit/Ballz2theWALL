"""Native MCP envelopes; preserve unrelated configuration and exact rollback plans.

Claude Code receives inline JSON on the managed launch command. Its settings.json
is not an MCP config and ~/.claude.json is outside the selected-home transaction.
"""
from __future__ import annotations

import os
import re
from collections.abc import MutableMapping
from pathlib import Path

from .config import Plan, encode, parse, set_dotted
from .machine import server_spec

SERVER_NAME = "ballz2thewall_machine"
# Only connection/routing metadata. Never serialize the whole environment or
# provider credentials into native agent configuration.
DESKTOP_ENV = (
    "DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "XDG_RUNTIME_DIR",
    "DBUS_SESSION_BUS_ADDRESS", "XDG_SESSION_TYPE", "PULSE_SERVER",
    "SystemRoot", "SYSTEMROOT", "WINDIR", "LOCALAPPDATA", "APPDATA", "TEMP", "TMP",
)


def binding_spec(state: Path, activation_id: str) -> dict:
    if not isinstance(activation_id, str) or not re.fullmatch(r"[0-9a-f]{32}", activation_id):
        raise ValueError("Invalid machine activation identity")
    spec = server_spec(state, activation_id)
    env = {key: os.environ[key] for key in DESKTOP_ENV if key in os.environ}
    if env:
        spec["env"] = env
    return spec


def claude_config(state: Path, activation_id: str) -> dict:
    return {"mcpServers": {SERVER_NAME: {"type": "stdio", **binding_spec(state, activation_id)}}}


def augment_plan(plan: Plan, state: Path, activation_id: str) -> Plan:
    """Add our uniquely owned server to a pending native config transaction.

    Never overwrite an existing namesake server, even if superficially similar.
    The activation controller handles idempotence against its saved receipt.
    """
    spec = binding_spec(state, activation_id)
    if plan.adapter == "claude":
        return plan
    if plan.adapter not in {"hermes", "codex", "openclaw"}:
        raise ValueError("Unsupported machine binding adapter")
    if plan.adapter == "openclaw":
        from .openclaw import parse_config
        data = parse_config(plan.after)
        path = f"mcp.servers.{SERVER_NAME}"
        spec.update(enabled=True, connectTimeout=30, timeout=120)
    else:
        data = parse(plan.after, plan.target.name)
        path = f"mcp_servers.{SERVER_NAME}"
        if plan.adapter == "hermes":
            spec.update(enabled=True, connect_timeout=30, timeout=120)
        else:
            spec.update(enabled=True, startup_timeout_sec=30, tool_timeout_sec=120)
    section = data
    for part in path.split(".")[:-1]:
        section = section.get(part, {})
        if not isinstance(section, MutableMapping):
            raise ValueError("Cannot patch a native MCP section that is not a mapping")
    if SERVER_NAME in section:
        raise ValueError("Native MCP server ballz2thewall_machine already exists; choose its owner before ON")
    set_dotted(data, path, spec)
    return Plan(plan.target, plan.before, encode(data, plan.target.name),
                {**plan.changes, path: spec}, plan.adapter)
