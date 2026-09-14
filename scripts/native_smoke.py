"""Optional native parser checks in isolated homes; no model or authentication calls."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

from ballz2thewall.adapters import ADAPTERS
from ballz2thewall.config import make_plan
from ballz2thewall.doctor import inspect_runtime
from ballz2thewall.store import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hermes-source", required=True, type=Path)
    parser.add_argument("--hermes-python", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    source = args.hermes_source.resolve()
    python = args.hermes_python.absolute()
    if not python.is_file():
        parser.error("--hermes-python must identify the installed runtime interpreter")
    reports = {}
    with tempfile.TemporaryDirectory(prefix="ballz-native-smoke-") as temp:
        root = Path(temp)
        state = Store(root / "state")
        for name, adapter in ADAPTERS.items():
            home = root / name
            receipt = state.apply(make_plan(adapter, home))
            reports[name] = inspect_runtime(adapter, home)
            assert reports[name]["status"] == "ready", reports[name]
            env = {key: os.environ[key] for key in ("PATH", "LANG") if key in os.environ}
            env.update({"HOME": str(root), adapter.home_env: str(home)})
            if name == "hermes":
                probe = '''import json
from hermes_cli.config import load_config_readonly, apply_terminal_config_to_env
from tools.approval_context import (_get_approval_mode, _get_cron_approval_mode,
                                   _get_single_query_approval_mode, _get_unattended_approval_mode)
cfg = load_config_readonly()
actual = {"mode": _get_approval_mode(), "cron": _get_cron_approval_mode(),
          "single": _get_single_query_approval_mode(), "unattended": _get_unattended_approval_mode(),
          "terminal": apply_terminal_config_to_env(env={})["TERMINAL_ENV"],
          "private_urls": cfg["security"]["allow_private_urls"]}
assert actual == {"mode": "off", "cron": "approve", "single": "approve",
                  "unattended": "approve", "terminal": "local", "private_urls": True}, actual
print(json.dumps(actual))
'''
                process = subprocess.run([str(python), "-c", probe], cwd=source, env=env,
                                         capture_output=True, text=True, timeout=60, check=True)
                reports[name]["effective_native_config"] = json.loads(process.stdout)
            elif name == "codex":
                command = [reports[name]["executable"], "features", "list"]
                valid = subprocess.run(command, cwd=root, env=env, capture_output=True, timeout=30)
                assert valid.returncode == 0, "Native Codex parser rejected generated config"
                target = home / adapter.filename
                original = target.read_bytes()
                try:
                    target.write_bytes(original.replace(b'"never"', b'"INVALID_BALLZ_TEST_POLICY"'))
                    invalid = subprocess.run(command, cwd=root, env=env, capture_output=True, timeout=30)
                    assert invalid.returncode != 0, "Negative control did not prove native config was loaded"
                finally:
                    target.write_bytes(original)
                reports[name]["native_parser"] = "accepted generated config; rejected invalid-policy control"
            else:
                reports[name]["native_parser"] = "not_verified; CLI help is not a settings-schema check"
            assert state.rollback(receipt["receipt_id"])["status"] == "rolled_back"
            reports[name]["isolated_apply_rollback"] = "passed"
    reports["model_execution"] = "not_tested"
    reports["browser_authentication"] = "not_tested"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(reports, indent=2) + "\n")
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
