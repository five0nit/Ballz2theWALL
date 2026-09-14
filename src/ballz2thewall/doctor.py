"""Probe installed command contracts without starting model sessions or reading auth."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from .adapters import Adapter


def inspect_runtime(adapter: Adapter, home: Path | None = None) -> dict:
    exe = shutil.which(adapter.executable)
    result = {"adapter": adapter.name, "executable": exe, "version": None,
              "tested_version": adapter.tested_version, "native_flag": adapter.flag,
              "flag_supported": False, "status": "missing", "auth": "not_probed"}
    if not exe:
        return result
    env = dict(os.environ)
    if home:
        env[adapter.home_env] = str(home)
    try:
        help_args = [exe, "chat", "--help"] if adapter.name == "hermes" else [exe, "--help"]
        help_run = subprocess.run(help_args, capture_output=True, text=True, timeout=30, env=env, check=False)
        version_run = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30, env=env, check=False)
        match = re.search(r"(?<![\w.])v?(\d+\.\d+\.\d+)\b", version_run.stdout)
        result["version"] = match.group(1) if match else None
        result["flag_supported"] = help_run.returncode == 0 and adapter.flag in help_run.stdout
        result["status"] = "ready" if result["flag_supported"] and version_run.returncode == 0 else "unsupported"
        result["version_match"] = result["version"] == adapter.tested_version
    except (OSError, subprocess.SubprocessError):
        result["status"] = "probe_failed"
    return result


def require_runtime(adapter: Adapter, home: Path) -> dict:
    report = inspect_runtime(adapter, home)
    if report["status"] != "ready":
        raise ValueError("Native runtime missing or incompatible; run ballz doctor")
    return report
