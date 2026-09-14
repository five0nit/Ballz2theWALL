# Verification — 0.1.1 local alpha

Local patch release following the late independent read-only code review. No live runtime profiles, credentials, gateways or browser sessions changed. No remote publication or global installation.

## Passing gates

- Source: **403 passed**, Python 3.13.14; zero failures, errors or skips.
- Fresh non-editable wheel: **403 passed**, Python 3.11.15; zero failures, errors or skips. Tests ran from `/tmp` with `PYTHONPATH` removed, pytest source injection disabled, and imports confirmed in `site-packages`.
- New late-review regression cases: **27**. Fault injection covers before/after rollback intent, restoration and completion, existing and newly created targets, restart recovery, legacy receipts and unrelated drift.
- Ruff: `All checks passed!` for `src`, `tests`, `scripts`. New test/probe files also passed format checking.
- Installed `ballz` and `ballz2thewall`: version checks, all adapter apply/idempotent-plan/dry-run/rollback round-trips and bundled skill install/rollback passed.
- Actual installed Hermes profile and terminal functions: **8 scope cases**, including unfixed negative controls, and **11 terminal cases** passed from both source and installed wheel. Helpers were extracted from native source via AST; resolver imports were real, not mocked. All homes were temporary. This was not full agent startup.
- Native Hermes 0.21.1 config/approval readers passed; Codex 0.152.0 accepted generated config and rejected an invalid-policy control. Claude Code 2.1.201 advertised its native permission flag. All isolated config rollbacks passed.

Machine evidence: [`verification/0.1.1/gates.json`](verification/0.1.1/gates.json), JUnit files, native source hashes and wheel-run output in that directory. `dist/RELEASE.json` binds final artifact hashes and commit after packaging.

## Review dispositions

1. **Sticky Hermes home redirection — fixed in 0.1.1.** Non-profile-shaped homes pass `--profile default`; named profile-shaped homes retain native early-return pinning. Launch and help/version probes use the same rule. Default, custom, nested and named homes tested; no marker edits.
2. **YAML alias mutation — already fixed in 0.1.0**, preserved and retested.
3. **Legacy terminal backend validation — fixed in 0.1.1.** `terminal.backend` wins over legacy `terminal.env_type`, matching native behavior.
4. **Valid CLI cwd rejection — fixed in 0.1.1.** The native local CLI replaces stored messaging cwd with process cwd. The earlier contradictory test and documentation were corrected; child `TERMINAL_CWD` remains pinned.
5. **Nonstandard JSON constants — already fixed in 0.1.0**, preserved and retested.
6. **Malformed receipt exceptions — already fixed in 0.1.0**, preserved and retested.
7. **Interrupted rollback acknowledgement — fixed in 0.1.1.** Persist `rolling_back` before restoration, recover either side of the write, and acknowledge exact original bytes/absence without rewriting. Legacy interrupted receipts supported; unrelated drift still rejected.
8. **Boolean/integer equality — already fixed in 0.1.0**, preserved and retested.

The read-only reviewer reported defects in the earlier snapshot, not approval of this final patch. Parent reproduced surviving failures and verified repairs directly. An initial native probe also falsified an overstrict nested-home rejection; that unnecessary guard was removed before release.

## Reproduce

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests scripts
.venv/bin/python -m build
uv venv --python python3.11 /tmp/ballz-clean-0.1.1
uv pip install --python /tmp/ballz-clean-0.1.1/bin/python \
  "$PWD/dist/ballz2thewall-0.1.1-py3-none-any.whl" pytest
REPO="$PWD"
cd /tmp
env -u PYTHONPATH /tmp/ballz-clean-0.1.1/bin/python "$REPO/scripts/package_smoke.py"
env -u PYTHONPATH /tmp/ballz-clean-0.1.1/bin/python -m pytest "$REPO/tests" -o pythonpath= -q
env -u PYTHONPATH /tmp/ballz-clean-0.1.1/bin/python "$REPO/scripts/native_scope_smoke.py" \
  --hermes-source /absolute/hermes-agent \
  --hermes-python /absolute/hermes-agent/venv/bin/python \
  --output /tmp/ballz-native-scopes.json
```

## Boundaries and retained evidence

- Live model execution, authenticated browser attachment and Claude native settings parsing remain unverified. Credential-manager integrations use labeled fixtures; no native auth store was read for this patch.
- Source-level function execution, native help/config probes, installed-package round-trips and model execution are distinct gates.
- No browser or external schema probe was rerun for this patch. Earlier evidence remains in [`VERIFICATION-0.1.0.md`](VERIFICATION-0.1.0.md); its cwd interpretation is explicitly superseded above.
- Native Windows writes unsupported; macOS unverified; remote CI not run. Controller locking does not eliminate races with unrelated native editors.
- Repo-first exception: narrow fixes inside the canonical MIT repository; no new dependencies or implementation base. Original discovery decision remains in `docs/discovery/DECISION.md`.
