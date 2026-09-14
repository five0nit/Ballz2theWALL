"""Run actual Hermes resolver/terminal functions in isolated fixture homes.

This deliberately extracts a narrow AST slice: no CLI startup, auth or model call.
Native imports inside those functions remain real; no resolver mocks are used.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import subprocess
import tempfile
from pathlib import Path

from ballz2thewall import cli
from ballz2thewall.adapters import get_adapter

PROBE = r"""
import ast, copy, json, os, re, sys
from pathlib import Path
payload = json.load(sys.stdin)
source = Path(payload["source"])
sys.path.insert(0, str(source))

def load_slice(relative, names):
    tree = ast.parse((source / relative).read_text())
    selected, found = [], set()
    for node in tree.body:
        keys = {node.name} if isinstance(node, ast.FunctionDef) else set()
        if isinstance(node, ast.Assign):
            keys = {t.id for t in node.targets if isinstance(t, ast.Name)}
        if keys & names:
            selected.append(node)
            found.update(keys & names)
    assert found == names, (relative, names - found)
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(source / relative), "exec"), globals())

load_slice("hermes_cli/main.py", {
    "_PROFILE_NAME_RE", "_inside_mcp_add_args", "_scan_profile_flag",
    "_resolve_sudo_user_profile_env", "_under_gateway_supervisor",
    "_desktop_ssh_backend", "_apply_profile_override"})
load_slice("cli.py", {"_TERMINAL_ENV_MAPPINGS", "_AUXILIARY_TASK_ENV",
                       "_CWD_PLACEHOLDERS", "_mirror_config_to_env"})
base_env = dict(os.environ)
scopes, terminals = [], []
for case in payload["scopes"]:
    os.environ.clear()
    os.environ.update(base_env)
    os.environ["HERMES_HOME"] = case["home"]
    sys.argv = list(case["argv"])
    _apply_profile_override()
    actual = os.environ["HERMES_HOME"]
    assert actual == case["expected"], (case["name"], actual, case["expected"])
    scopes.append({"case": case["name"], "matched": True})
for case in payload["terminals"]:
    os.environ.clear()
    os.environ.update(base_env)
    os.environ.update({"TERMINAL_ENV": "local", "TERMINAL_CWD": "/stale/parent/cwd"})
    defaults = {"terminal": copy.deepcopy(case["config"])}
    _mirror_config_to_env(defaults, True)
    actual = os.environ["TERMINAL_ENV"]
    assert (actual == "local") == (case["ballz_exit"] == 0), case
    if case["ballz_exit"] == 0:
        assert os.environ["TERMINAL_CWD"] == os.getcwd(), case
    terminals.append({"config": case["config"], "native_backend": actual,
                      "ballz_exit": case["ballz_exit"], "matched": True})
print(json.dumps({"scope_cases": scopes, "terminal_cases": terminals,
                  "execution": "isolated installed-native function slices; no CLI startup"}))
"""


def dry_run(home: Path, cwd: Path) -> tuple[int, dict]:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = cli.main(
            ["run", "hermes", "--home", str(home), "--cwd", str(cwd), "--prompt", "fixture only", "--dry-run"]
        )
    return code, json.loads(output.getvalue())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hermes-source", required=True, type=Path)
    parser.add_argument("--hermes-python", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    source = args.hermes_source.resolve()
    adapter = get_adapter("hermes")
    old_home = os.environ.get("HOME")
    try:
        with tempfile.TemporaryDirectory(prefix="ballz-native-scope-") as temp:
            root = Path(temp)
            user = root / "user"
            os.environ["HOME"] = str(user)
            default = user / ".hermes"
            payload = {"source": str(source), "scopes": [], "terminals": []}
            for name, home in [
                ("custom_root", root / "custom"),
                ("default_root", default),
                ("nested_root", default / "staging"),
                ("custom_named", root / "custom/profiles/chosen"),
                ("default_named", default / "profiles/chosen"),
            ]:
                (home / "profiles/other").mkdir(parents=True)
                marker = home / "active_profile"
                marker.write_text("other\n")
                code, result = dry_run(home, root)
                assert code == 0, result
                payload["scopes"].append(
                    {"name": name, "home": str(home), "argv": result["argv"], "expected": str(home)}
                )
                if home.parent.name != "profiles":
                    payload["scopes"].append(
                        {
                            "name": name + "_unfixed_control",
                            "home": str(home),
                            "argv": adapter.argv(interactive=False),
                            "expected": str(home / "profiles/other"),
                        }
                    )
                assert marker.read_text() == "other\n"
            terminal_home = root / "terminal"
            terminal_home.mkdir()
            for config in [
                {},
                {"env_type": "docker"},
                {"env_type": "ssh"},
                {"backend": "local", "env_type": "docker"},
                {"backend": "docker", "env_type": "local"},
                {"backend": "local", "cwd": "/other/project"},
                {"env_type": "local", "cwd": "child"},
                *[{"cwd": v} for v in [None, 1, True, []]],
            ]:
                (terminal_home / "config.yaml").write_text(json.dumps({"terminal": config}))
                code, _ = dry_run(terminal_home, root)
                payload["terminals"].append({"config": config, "ballz_exit": code})
            env = {k: os.environ[k] for k in ("PATH", "LANG") if k in os.environ}
            env.update(
                {"HOME": str(user), "HERMES_HOME": str(root / "custom"), "PYTHONDONTWRITEBYTECODE": "1"}
            )
            process = subprocess.run(
                [str(args.hermes_python.absolute()), "-c", PROBE],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                cwd=root,
                env=env,
                timeout=60,
                check=False,
            )
            if process.returncode:
                raise SystemExit(f"Native fixture probe failed ({process.returncode}):\n{process.stderr}")
            report = json.loads(process.stdout)
    finally:
        if old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = old_home
    report["native_source_sha256"] = {
        path: hashlib.sha256((source / path).read_bytes()).hexdigest()
        for path in [
            "hermes_cli/main.py",
            "hermes_cli/_parser.py",
            "hermes_cli/profiles.py",
            "hermes_constants.py",
            "cli.py",
        ]
    }
    report["model_execution"] = "not_tested"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
