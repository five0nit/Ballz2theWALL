# OpenClaw adapter — 0.2.0a2

## Supported contract

An already-installed, authenticated OpenClaw CLI on Linux, WSL, or macOS.
First native acceptance: **OpenClaw 2026.6.1**. Native Windows is rejected;
install Ballz inside WSL to operate a WSL OpenClaw installation. The native
Windows setup does not cross into WSL. macOS source compatibility is implemented;
physical Mac acceptance is still pending.

Use a state directory named `.openclaw`, normally `$HOME/.openclaw`. Named
profiles and arbitrary custom state-directory names are rejected. OpenClaw
2026.6.1 resolves approvals through `OPENCLAW_HOME/.openclaw/exec-approvals.json`
independently of `OPENCLAW_STATE_DIR`; Ballz pins both resolvers to one selected
home and verifies the exact native approval path. No symlink workaround.

```bash
ballz plan openclaw --home "$HOME/.openclaw"
ballz on openclaw --home "$HOME/.openclaw"
ballz run openclaw --home "$HOME/.openclaw" --cwd "$PWD" --interactive
# Close the agent first:
ballz off
```

`apply`/`rollback RECEIPT_ID` also work for explicit non-managed transactions.
`run` itself never persists settings and requires an already-applied ON policy.

## What changes

- `openclaw.json` (JSON5 input, strict JSON output): full tool profile and wildcard
  allow, configured tool deny list cleared, local host `gateway`, full exec mode,
  sandbox off, filesystem/apply-patch workspace-only restrictions off.
- Existing per-agent tool policies receive the same requested policy.
- `exec-approvals.json`: full execution / ask off / fallback full at defaults,
  wildcard agent and existing agent entries. Existing socket and allowlist data
  retained. Gateways/nodes are not started, stopped, reconfigured or contacted.
- Model providers, channel definitions and existing authentication remain native;
  Ballz does not read OAuth stores or copy credentials. JSON formatting/comments
  can change on ON. OFF restores exact original bytes or original absence.

Remote execution hosts, included/external config fragments, provider-specific
policy maps and unsupported per-agent runtime forms are rejected, not flattened.
This is host-wide local exec approval policy, not a per-process permission token.
Close existing agents before switching ON/OFF; other native editors do not take
Ballz's advisory lock. Future or running native readers can observe config changes.

## Verification and recovery

ON validates with native `config validate --json` and `exec-policy show --json`.
It checks the exact approvals path and every reported effective agent policy,
not just a CLI exit status. Native validation failure compensates both files.
The store journals every step and supports interruption/retry without overwriting
later user edits. This is a recoverable two-file transaction, not an atomic
filesystem transaction. Backups stay in the private local state directory.

The terminal loop forwards messages to native `agent --local --agent main`
(or the configured default agent) under one generated session ID. No gateway
service or additional model harness. Native OpenClaw accepts text through
`--message`, so prompts are visible in process arguments; dry-run redacts them.
OpenClaw's configured workspace and session rules remain native; `--cwd` sets
the child process directory, not an override of its agent workspace setting.

`scripts/openclaw_native_smoke.py` exercises empty and configured scratch homes,
strict native schema/effective policies, byte-exact OFF, and a negative mixed
legacy/new-policy control. It never invokes a model, reads a live home, starts a
gateway or changes OS permissions. Model-authenticated tasks and physical Mac
permissions are separate acceptance steps and are not claimed as verified.

## Source evidence

Native contracts inspected in OpenClaw 2026.6.1 `dist/paths-*.js`,
`dist/exec-approvals-*.js`, `dist/exec-policy-cli-*.js`, and shipped docs:
[exec approvals](https://docs.openclaw.ai/tools/exec-approvals),
[exec policy](https://docs.openclaw.ai/cli/approvals),
[agent CLI](https://docs.openclaw.ai/cli/agent).
