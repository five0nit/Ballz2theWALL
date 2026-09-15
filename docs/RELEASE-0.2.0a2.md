# Ballz2theWALL 0.2.0a2 — OpenClaw + guided-install hardening

Unsigned public alpha. Install. Approve. Turn ON.

## Added

- Native OpenClaw local embedded adapter with JSON5 config support, coordinated
  config/host-approval journals, effective native-policy verification and exact OFF restoration.
- Guided discovery and terminal prompt forwarding; existing authentication stays with OpenClaw.
- Branded, dependency-free info page with accessible interactive switch preview.
- Native Windows CI lane and expanded installer integrity/platform regression coverage.

## Improved

Mac isolated Python launch chain and early prerequisite checks; Windows installer
preflight, production shortcut readback and success-only receipt documentation.
Installer bundles use one immutable wheel snapshot and validated SHA-256 manifests.
Hermes, OpenAI Codex and Claude Code support retained.

## Verification

537 source tests and 537 fresh-wheel tests passed (4 platform/opt-in skips each).
77 OpenClaw tests; 10 native OpenClaw 2026.6.1 smoke checks; 13 native Windows installer
checks; 48 native Windows installed-wheel core/store/installer tests (2 platform/opt-in skips).
Independent spec and code-quality reviews passed. Full evidence in docs/VERIFICATION.md.

## Scope

OpenClaw: Linux/WSL verified; standard `.openclaw` home only; embedded local runs.
Native Windows, named/custom profiles, remote/node execution, provider-specific tools
and explicit per-agent runtime overrides are not supported by this adapter.
Mac hardware acceptance and permission attribution remain pending. The Mac ZIP is
experimental, unsigned and not notarized. No universal desktop-control claim.
No live authenticated model execution was part of this release verification.

OFF restores previous stored settings, not running processes or completed work.
