"""Format-aware patches that retain unrelated values and never print old values."""
from __future__ import annotations

import json
from collections.abc import MutableMapping
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tomlkit
import yaml

from .adapters import Adapter


class UniqueLoader(yaml.SafeLoader):
    pass


def unique_yaml(loader, node, deep=False):
    loader.flatten_mapping(node)
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ValueError("Duplicate YAML key")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_yaml)


def unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def invalid_json_constant(value: str):
    raise ValueError("Nonstandard JSON constant")


def parse(data: bytes, filename: str) -> MutableMapping:
    try:
        text = data.decode("utf-8")
        if filename.endswith(".yaml"):
            result = yaml.load(text, Loader=UniqueLoader) if text.strip() else {}
        elif filename.endswith(".toml"):
            result = tomlkit.parse(text)
        else:
            result = json.loads(text, object_pairs_hook=unique_json,
                                parse_constant=invalid_json_constant) if text.strip() else {}
        if not isinstance(result, MutableMapping):
            raise ValueError("Expected a mapping")
        return result
    except (ValueError, TypeError, UnicodeError, yaml.YAMLError, tomlkit.exceptions.ParseError, RecursionError):
        # Parser diagnostics can quote an API key from the source line.
        raise ValueError("Invalid native config: expected valid UTF-8 mapping without duplicate keys") from None


def encode(data: MutableMapping, filename: str) -> bytes:
    if filename.endswith(".yaml"):
        text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    elif filename.endswith(".toml"):
        text = tomlkit.dumps(data)
    else:
        text = json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    return text.encode("utf-8")


def set_dotted(data: MutableMapping, key: str, value: Any) -> bool:
    parts = key.split(".")
    for part in parts[:-1]:
        if part not in data:
            data[part] = {}
        if not isinstance(data[part], MutableMapping):
            raise ValueError("Cannot patch a native config section that is not a mapping")
        # Detach YAML aliases so patching one section cannot edit another.
        data[part] = deepcopy(data[part])
        data = data[part]
    previous = data.get(parts[-1])
    changed = (parts[-1] not in data or previous != value
               or isinstance(previous, bool) != isinstance(value, bool))
    data[parts[-1]] = value
    return changed


def checked_path(path: Path) -> Path:
    path = path.expanduser().absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Target must not be a symlink; pass its explicit real path")
    if path.exists() and not path.is_file():
        raise ValueError("Target exists but is not a regular file")
    return path


@dataclass
class Plan:
    target: Path
    before: bytes | None = field(repr=False)
    after: bytes = field(repr=False)
    changes: dict[str, Any]
    adapter: str

    def public(self) -> dict:
        return {"adapter": self.adapter, "target": str(self.target), "changed": self.before != self.after,
                "settings": self.changes, "scope": "selected native home only",
                "activation": "future processes; running agents unchanged"}


def make_plan(adapter: Adapter, home: Path, cdp: str | None = None,
              inherit_secrets: bool = False) -> Plan:
    target = checked_path(home / adapter.filename)
    before = target.read_bytes() if target.exists() else None
    data = parse(before or b"", adapter.filename)
    if adapter.name == "codex" and "default_permissions" in data:
        raise ValueError("Codex default_permissions conflicts with sandbox_mode; use run instead or migrate explicitly")
    values = adapter.settings(cdp, inherit_secrets)
    changed = False
    for key, value in values.items():
        changed = set_dotted(data, key, value) or changed
    after = encode(data, adapter.filename) if changed or before is None else before
    return Plan(target, before, after, values, adapter.name)
