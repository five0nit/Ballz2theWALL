# Verification — 0.1.0 local alpha

Verified on Linux/WSL on 2026-09-15. No live agent profile, gateway, authentication store or default browser profile was modified. No remote repository, registry publication or machine-wide installation was performed.

## Passing gates

- Source suite: **376 passed**, Python **3.13.14**; no failures, errors or skips.
- Fresh non-editable wheel suite: **376 passed**, Python **3.11.15**; no failures, errors or skips. Executed from `/tmp` with `PYTHONPATH` removed and pytest's source `pythonpath` setting disabled.
- Ruff: `All checks passed!` for `src`, `tests`, and `scripts`.
- Wheel and source distribution build: passed with isolated Hatchling build environments.
- Installed `ballz` and `ballz2thewall` console scripts: version checks passed.
- Installed-package local round-trips: Hermes, Codex and Claude config apply, idempotent plan, dry-run launch, rollback; bundled skill install and rollback.
- Native Hermes **0.21.1**: isolated-home native config readers confirmed approval mode `off`; cron, unattended and single-query modes `approve`; terminal backend `local`; private URL access enabled.
- Native Codex **0.152.0**: `features list` accepted generated config and rejected an invalid-policy negative control, proving that the selected config was actually loaded.
- Claude Code **2.1.201**: installed help advertises the native permission flag. Generated settings passed the SchemaStore Claude settings schema; an invalid permission-mode control failed. **This is not proof of Claude's native settings parser.**
- Codex generated config passed the official OpenAI JSON Schema; invalid-policy control failed.
- Real isolated Chrome **147.0.7727.55**: version endpoint returned protocol **1.3**. Only `/json/version` metadata was requested. Temporary process group and empty profile were removed. An earlier teardown raced Chrome's profile writes; the process-group-managed repeat passed including cleanup.

Machine-readable gate evidence is in `verification/gates.json`. Release artifact hashes are recorded separately in `dist/RELEASE.json` after final packaging, avoiding self-referential archive hashes.

## Final-review corrections

Regression tests first reproduced defects; production fixes then passed the full suites:

1. Pin Hermes `TERMINAL_CWD` to the selected child working directory; reject conflicting native paths and invalid value types. Evaluate relative native paths from the child's directory, not the controller's parent directory.
2. Validate rollback receipt mappings, required fields, path shape, statuses, hash syntax and mode types before file operations. Malformed records produce controlled CLI errors rather than uncaught tracebacks.
3. Reject nonstandard JSON constants and avoid emitting nonstandard JSON during config updates.

Earlier regressions also cover YAML alias detachment and boolean-versus-integer settings equality. Saved delegated work was recovered and directly tested. A timed-out worker is not counted as an independent review approval.

## Evidence boundaries

- Real model execution: **not tested**. Subprocess transport tests use clearly identified local fixtures; they prove stdin/environment/exit-code behavior, not model authentication or provider access.
- Credential bindings: real environment lookup and local child-process transport tested; 1Password and keyring success/error paths tested with fixtures. No live password-manager account was unlocked or read.
- Authenticated Chrome browsing, Claude extension pairing, Codex browser MCP: **not tested**. Browser metadata does not prove a site login or runtime attachment.
- Claude native settings parsing: **not verified**. SchemaStore validation and CLI help are separate evidence.
- Native Windows write/rollback: **not implemented**. macOS: **unverified**.
- GitHub Actions workflow supplied, but remote CI: **not run**.
- Provider policy, OS elevation, instruction-file guards and browser-saved-password extraction are outside this implementation.

## Reproduce

From the repository:

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests scripts
.venv/bin/python -m build

# Use a new empty environment path, not an existing editable installation.
uv venv --python python3.11 /tmp/ballz-clean-check
uv pip install --python /tmp/ballz-clean-check/bin/python \
  "$PWD/dist/ballz2thewall-0.1.0-py3-none-any.whl" pytest
REPO="$PWD"
cd /tmp
env -u PYTHONPATH /tmp/ballz-clean-check/bin/python "$REPO/scripts/package_smoke.py"
env -u PYTHONPATH /tmp/ballz-clean-check/bin/python -m pytest \
  "$REPO/tests" -o pythonpath= -q
```

Optional installed-runtime checks, using the actual installed Hermes paths:

```bash
.venv/bin/python scripts/native_smoke.py \
  --hermes-source /absolute/hermes-agent \
  --hermes-python /absolute/hermes-agent/venv/bin/python \
  --output /tmp/ballz-native-smoke.json
```

This probe uses empty temporary runtime homes and does not invoke a model. It records Claude's native-parser gap rather than substituting help output for a passing parser check.
