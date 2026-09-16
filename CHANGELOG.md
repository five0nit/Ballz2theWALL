# Changelog

Published downloads and unreleased source changes are listed separately. Evidence
is scoped to the version actually exercised; older results do not certify newer
source or rebuilt artifacts.

## 0.3.0a0.dev6 — unreleased development candidate

### Added since the published alpha

- Managed machine MCP with command execution, bounded file operations and dynamic
  `desktop_` tools from pinned cua-driver 0.28.1; mcp 1.30.0 is also required.
- Native Hermes/Codex machine bindings, Claude launch-time `--mcp-config`, and
  a local OpenClaw binding subject to native schema/policy validation.
- Explicitly approved, activation-bound Windows Administrator helper. No silent
  elevation or persistent system service.
- Session-owned background commands with live output, status and cancellation.
  Both account-rights and approved Administrator jobs are supported.
- Pending Windows approval recovery: revoke an old reservation before retrying UAC.

### Hardened across the development candidates

- OFF revokes managed tool access before exact configuration restoration; command
  cancellation and driver/helper cleanup follow the activation lifecycle.
- Long-command deadlines accept zero for no deadline. Background jobs avoid holding
  one MCP request open for the command duration; client request limits still apply.
- Command-reader startup cleanup, bounded output capture, decimal wire handling,
  large-timeout handling, and strict installer component/readiness validation.
- Consumer docs now distinguish machine capability, native parsing, saved automated
  evidence and remaining live owner/distribution acceptance.

### Verification and release boundary

Saved dev6 receipts record **917 passed, 4 skipped** for source and separately for
a clean installed wheel; native Windows scope records **241 passed, 1 skipped**.
Real non-elevated 125-second jobs and isolated Windows install/reinstall passed.
These are existing results, not a claim that this documentation update reran them.

Dev6 has **no installer release or final owner acceptance**. Genuine UAC/elevated-job cleanup,
signed-in browser access, current authenticated-agent/OFF restoration, normal
downloaded installation, physical Mac acceptance and distribution/license gates
remain open. See [verification](docs/VERIFICATION.md) and
[capabilities](docs/CONSUMER-ACCESS.md).

## 0.2.0a2 — current published unsigned alpha

[Release and downloads](https://github.com/five0nit/Ballz2theWALL/releases/tag/v0.2.0a2)

- Native runtime full-access configuration and launch adapters for Hermes, Codex,
  Claude Code and the scoped local OpenClaw contract.
- Guided Windows/Mac installation, private Python bootstrap, ON/OFF journals,
  credential references and reversible local receipts.
- Native Windows installer/store and OpenClaw policy checks; physical Mac
  acceptance remained pending.

This earlier release does **not** include dev6 machine MCP, desktop bridge,
Windows helper or background command jobs. Its original verification page is
preserved unchanged at [VERIFICATION-0.2.0a2.md](docs/VERIFICATION-0.2.0a2.md).
Earlier evidence: [0.2.0a1](docs/VERIFICATION-0.2.0a1.md) and
[0.1.1](docs/VERIFICATION-0.1.1.md).
