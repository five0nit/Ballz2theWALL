"""Native OpenClaw schema/policy/activation smoke. Scratch only; no model calls."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from ballz2thewall.adapters import get_adapter
from ballz2thewall.doctor import require_runtime
from ballz2thewall.onboarding import Activation
from ballz2thewall.openclaw import make_plans
from ballz2thewall.openclaw_runtime import verify_native
from ballz2thewall.store import digest


def main():
    with tempfile.TemporaryDirectory(prefix="ballz-openclaw-native-") as temporary:
        root = Path(temporary)
        home = root / ".openclaw"
        home.mkdir()
        # Pin every native home lookup to scratch, including host approvals.
        os.environ.update(HOME=str(root), OPENCLAW_HOME=str(root), OPENCLAW_STATE_DIR=str(home),
                          OPENCLAW_CONFIG_PATH=str(home / "openclaw.json"),
                          OPENCLAW_OAUTH_DIR=str(home / "credentials"))
        before = [b'''// synthetic JSON5 fixture; no credentials
{ agents: { defaults: {sandbox:{mode:'all'}}, list:[{id:'main',default:true,tools:{exec:{security:'deny',ask:'always'}}}] },
  tools: {profile:'messaging',allow:['read'],deny:['exec'],exec:{host:'sandbox',security:'deny',ask:'always'}} }
''', b'{"version":1,"defaults":{"security":"deny","ask":"always"},"agents":{"main":{"security":"deny","ask":"always"}}}\n']
        targets = [home / "openclaw.json", home / "exec-approvals.json"]
        for path, data in zip(targets, before, strict=True):
            path.write_bytes(data)
        report = require_runtime(get_adapter("openclaw"), home)
        control = Activation(root / "control")
        on = control.enable("openclaw", home)
        assert on["phase"] == "on"
        verification = verify_native(home, report["executable"])
        assert verification["effective_scopes"] >= 2
        assert control.enable("openclaw", home) == on
        assert all(p.before == p.after for p in make_plans(home))
        changed = targets[1].read_bytes()
        data = json.loads(changed)
        data["defaults"]["security"] = "deny"
        data["agents"]["main"]["security"] = "deny"
        targets[1].write_text(json.dumps(data))
        try:
            verify_native(home, report["executable"])
        except ValueError:
            pass
        else:
            raise AssertionError("Native effective policy accepted restrictive host")
        targets[1].write_bytes(changed)
        assert control.disable()["phase"] == "off"
        assert [p.read_bytes() for p in targets] == before
        assert control.disable()["phase"] == "off"
        # Native negative control: new and legacy policy syntax conflict.
        targets[0].write_text('{"tools":{"exec":{"mode":"full","security":"full"}}}')
        invalid = subprocess.run([report["executable"], "config", "validate", "--json"],
                                 capture_output=True, text=True, timeout=45, check=False)
        assert invalid.returncode != 0 and json.loads(invalid.stdout)["valid"] is False
        try:
            require_runtime(get_adapter("openclaw"), root / ".openclaw-other")
        except ValueError:
            pass
        else:
            raise AssertionError("Named profile mismatch was accepted")
        # Ambient overrides must not redirect the configured approval file.
        os.environ["OPENCLAW_HOME"] = str(root / "wrong")
        for plan in make_plans(home):
            plan.target.write_bytes(plan.after)
        assert verify_native(home, report["executable"])["native_config_valid"]
        result = {"runtime": report["version"], "cases": ["native_flag_detection", "multi_scope_ON",
                   "native_effective_policy", "idempotent_ON", "restrictive_host_negative",
                   "exact_byte_OFF", "idempotent_OFF", "native_schema_negative",
                   "named_profile_rejected", "ambient_home_override_pinned"],
                  "verification": verification, "before_sha256": [digest(b) for b in before],
                  "model_calls": 0, "real_profile_changes": 0, "gateway_restarts": 0,
                  "native_executable_detected": bool(shutil.which("openclaw"))}
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
