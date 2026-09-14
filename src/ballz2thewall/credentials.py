"""Resolve only explicit credential references; never inspect browser auth stores."""

from __future__ import annotations

import os
import re
import subprocess
import unicodedata
from importlib import import_module

_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*", re.ASCII)
_OP_TIMEOUT_SECONDS = 15
_INVALID_BINDINGS = "Invalid credential bindings"
_RESOLUTION_FAILED = "Credential resolution failed"


def _has_control(value: str) -> bool:
    # Reject controls (including NUL) and invalid Unicode scalar values without
    # trimming or otherwise changing a credential destined for subprocess env.
    return any(unicodedata.category(char) in {"Cc", "Cs"} for char in value)


def _parse_bindings(bindings: list[str]) -> list[tuple[str, str, str]]:
    if not isinstance(bindings, list):
        raise ValueError(_INVALID_BINDINGS)
    parsed = []
    names = set()
    for binding in bindings:
        if not isinstance(binding, str) or _has_control(binding):
            raise ValueError(_INVALID_BINDINGS)
        name, equals, source = binding.partition("=")
        provider, colon, reference = source.partition(":")
        if not equals or not colon or not _ENV_NAME.fullmatch(name) or name in names:
            raise ValueError(_INVALID_BINDINGS)
        if provider == "env":
            valid = bool(_ENV_NAME.fullmatch(reference))
        elif provider == "op":
            # Official 1Password references support an optional section name.
            parts = reference.removeprefix("op://").split("/")
            valid = (
                reference.startswith("op://") and len(parts) in (3, 4) and all(part.strip() for part in parts)
            )
        elif provider == "keyring":
            service, slash, account = reference.partition("/")
            valid = bool(slash and service.strip() and account.strip())
        else:
            valid = False
        if not valid:
            raise ValueError(_INVALID_BINDINGS)
        names.add(name)
        parsed.append((name, provider, reference))
    return parsed


def describe_bindings(bindings: list[str]) -> list[dict[str, str]]:
    """Validate the complete list without reading any credential or provider."""
    return [{"env": name, "provider": provider} for name, provider, _ in _parse_bindings(bindings)]


def _read_value(provider: str, reference: str) -> str:
    try:
        if provider == "env":
            value = os.environ.get(reference)
        elif provider == "op":
            # Use the official CLI's existing authenticated session. No shell,
            # sign-in flow, stdin prompt, or manager diagnostic is propagated.
            result = subprocess.run(
                ["op", "read", reference],
                shell=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=_OP_TIMEOUT_SECONDS,
                check=True,
            )
            # Byte capture avoids universal-newline rewriting of the secret.
            # Remove exactly the single LF appended by `op read`, not whitespace.
            value = result.stdout.removesuffix(b"\n").decode("utf-8")
        else:
            service, _, account = reference.partition("/")
            value = import_module("keyring").get_password(service, account)
    except Exception:
        # Optional keyring backends have provider-specific exception classes;
        # none of their messages (or chained tracebacks) are safe to expose.
        raise ValueError(_RESOLUTION_FAILED) from None
    if not isinstance(value, str) or not value or _has_control(value):
        raise ValueError(_RESOLUTION_FAILED)
    return value


def resolve_bindings(bindings: list[str]) -> dict[str, str]:
    """Resolve validated references into a new mapping, leaving inherited env intact."""
    parsed = _parse_bindings(bindings)
    return {name: _read_value(provider, reference) for name, provider, reference in parsed}
