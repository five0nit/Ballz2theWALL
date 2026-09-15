"""Exercise an installed wheel outside its source tree; no agent login required."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import ballz2thewall
from ballz2thewall.adapters import ADAPTERS
from ballz2thewall.config import make_plan
from ballz2thewall.store import Store


def main():
    module_file = ballz2thewall.__file__
    assert module_file is not None
    module_path = Path(module_file).resolve()
    if "site-packages" not in module_path.parts:
        raise SystemExit("Run with a non-editable installed wheel, outside source imports")
    with tempfile.TemporaryDirectory(prefix="ballz-wheel-smoke-") as temp:
        root = Path(temp)
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        for name in ("ballz", "ballz2thewall"):
            entrypoint = Path(sys.executable).parent / name
            version = subprocess.run([str(entrypoint), "--version"], capture_output=True, text=True,
                                     cwd=root, env=env, check=True)
            assert version.stdout.strip() == f"Ballz2theWALL {ballz2thewall.__version__}"
        results = []
        for name, adapter in ADAPTERS.items():
            if name == "openclaw":
                continue  # Separate two-file round trip below.
            home = root / name
            plan = make_plan(adapter, home)
            state = Store(root / "state")
            receipt = state.apply(plan)
            assert make_plan(adapter, home).public()["changed"] is False
            result = subprocess.run(
                [sys.executable, "-m", "ballz2thewall", "plan", name, "--home", str(home)],
                capture_output=True, text=True, cwd=root, env=env, check=True,
            )
            assert json.loads(result.stdout)["changed"] is False
            launch = subprocess.run(
                [sys.executable, "-m", "ballz2thewall", "run", name, "--home", str(home),
                 "--cwd", str(root), "--prompt", "local package smoke", "--dry-run"],
                capture_output=True, text=True, cwd=root, env=env, check=True,
            )
            assert json.loads(launch.stdout)["status"] == "dry_run"
            state.rollback(receipt["receipt_id"])
            assert not (home / adapter.filename).exists()
            results.append({"adapter": name, "roundtrip": "passed", "launch": "dry_run_only"})
        from ballz2thewall.openclaw import OpenClawStore, make_plans
        home = root / ".openclaw"
        state = OpenClawStore(root / "openclaw-state")
        receipt = state.apply(make_plans(home))
        assert not any(p.public()["changed"] for p in make_plans(home))
        result = subprocess.run(
            [sys.executable, "-I", "-m", "ballz2thewall", "plan", "openclaw", "--home", str(home)],
            capture_output=True, text=True, cwd=root, env=env, check=True)
        assert all(not p["changed"] for p in json.loads(result.stdout)["files"])
        state.rollback(receipt["receipt_id"])
        assert all(not (home / filename).exists() for filename in ("openclaw.json", "exec-approvals.json"))
        results.append({"adapter": "openclaw", "roundtrip": "passed", "launch": "not_invoked"})
        result = subprocess.run(
            [sys.executable, "-m", "ballz2thewall", "skill", "--dest", str(root / "skills"),
             "--state-dir", str(root / "state")],
            capture_output=True, text=True, cwd=root, env=env, check=True,
        )
        receipt = json.loads(result.stdout)
        assert "name: ballz2thewall" in (root / "skills/ballz2thewall/SKILL.md").read_text()
        Store(root / "state").rollback(receipt["receipt_id"])
        print(json.dumps({"package": str(module_path), "python": sys.version.split()[0],
                          "adapters": results, "bundled_skill_roundtrip": "passed"}, indent=2))


if __name__ == "__main__":
    main()
