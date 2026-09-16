"""Bounded installer readiness; no activation, desktop actions or permission requests."""
from __future__ import annotations

import subprocess
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version

from .machine import desktop_spec

EXPECTED = {"mcp": ("1.30.0", "mcp"), "cua-driver": ("0.28.1", "cua_driver")}


def inspect_machine() -> dict:
    report = {"schema": 1, "status": "unavailable", "packages": {}, "desktop_driver": {},
              "errors": [], "scope": "dependencies_and_native_executable_only",
              "live_permissions": "not_tested"}
    for package, (expected, module) in EXPECTED.items():
        item = {"expected": expected, "installed": None, "importable": False}
        report["packages"][package] = item
        try:
            item["installed"] = version(package)
            import_module(module)
            item["importable"] = True
            if item["installed"] != expected:
                report["errors"].append(f"{package} must be version {expected}; reinstall Ballz2theWALL")
        except (PackageNotFoundError, ImportError, OSError):
            report["errors"].append(f"{package} is missing or cannot load; reinstall Ballz2theWALL")
    try:
        command = desktop_spec()["command"]
        result = subprocess.run([command, "--version"], stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, timeout=10)
        observed = result.stdout.strip()
        ready = result.returncode == 0 and observed == "cua-driver " + EXPECTED["cua-driver"][0]
        report["desktop_driver"] = {"command": command, "version": observed[:200],
                                    "status": "ready" if ready else "unavailable"}
        if not ready:
            report["errors"].append("Native desktop executable failed its version check; reinstall Ballz2theWALL")
    except (ValueError, OSError, subprocess.SubprocessError):
        report["desktop_driver"] = {"status": "unavailable"}
        report["errors"].append("Native desktop executable is unavailable; reinstall Ballz2theWALL")
    if not report["errors"]:
        report["status"] = "ready"
    return report


def require_ready() -> dict:
    report = inspect_machine()
    if report["status"] != "ready":
        raise ValueError("Machine tools are not ready. Reinstall Ballz2theWALL, then reopen setup. "
                         + " ".join(report["errors"]))
    return report
