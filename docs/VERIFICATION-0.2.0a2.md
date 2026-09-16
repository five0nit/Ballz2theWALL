# Verification — 0.2.0a2 unsigned alpha

Machine-readable evidence: [gates.json](verification/0.2.0a2/gates.json).
Previous evidence remains under [0.2.0a1](VERIFICATION-0.2.0a1.md) and
[0.1.1](VERIFICATION-0.1.1.md); old artifacts were not replaced.

## Passing release gates

- Source: **537 passed, 4 skipped**. Ruff and whitespace checks passed.
- Fresh, non-editable Python 3.11 wheel: **537 passed, 4 skipped**. Both installed
  console entrypoints, four adapters' scratch round trips, and bundled skill
  install/rollback exercised outside source imports.
- OpenClaw targeted tests: **77 passed**. Independent spec review PASS and
  code-quality review APPROVED; final reviewer independently ran the same 77 tests.
- Native OpenClaw **2026.6.1**: **10 checks** including real CLI capability detection,
  native config validation, two effective policy scopes, ON/OFF idempotence,
  byte-identical restoration, restrictive-policy/schema negative controls,
  unsupported profile rejection and ambient-home override pinning.
- Native Windows x64 installer: **13 passed**, including private Python bootstrap,
  wheel install, reinstall, source fallback, no global PATH or Start Menu changes,
  PowerShell parsing, invalid-payload controls and COM shortcut readback.
- Native Windows installed-wheel core/store/installer: **48 passed, 2 skipped**. Eight native
  store smoke groups pass; Windows ACLs are checked as ACLs, not POSIX bits.
- Info page: four browser cases at 1440, 390 and 320 CSS pixels; keyboard/touch preview
  switch, FAQ disclosure, download anchor, reduced motion and no-JavaScript fallback.
  No horizontal overflow or console errors. Desktop and phone screenshots visually reviewed.
- ZIP contents, Mac executable bit, SHA-256 manifests and embedded wheel equality checked.

Source/fresh-wheel skips are the opt-in network installation test and native-only
Windows tests. Installation and Windows cases are exercised separately.
The two native-Windows skips are the POSIX permission-mode test and the separately
executed opt-in installation test.

## Audit corrections

- Removed incompatible legacy exec security/ask fields when writing modern OpenClaw mode.
- Pinned its separate native approval-home resolver; named/custom layouts are rejected.
- Reject explicit ACP/other per-agent runtime overrides before writes.
- Hardened Mac interpreter isolation and preflight; tested immutable installer wheel snapshots.
- Corrected narrow-phone heading overflow and platform-specific test expectations.
- First WSL-to-Windows invocation failed with `UtilAcceptVsock` before application
  execution. The complete installer suite was rerun successfully; failures were not reclassified.
- Historical secret scan: three false positives individually examined: two source-file
  SHA-256 metadata entries and one printed CLI credential-reference syntax. Exact
  historical fingerprints alone are allowlisted in `.gitleaksignore`; no path-wide exemptions.

GitHub clean-runner failures additionally exposed a Windows-toolchain skip-order
bug, default Administrators ownership on elevated lock-file creation, and a
PowerShell 7 module-path inheritance conflict. Fixed with early toolchain checks,
explicit current-user lock descriptors and a temporary built-in module path.
Regression tests preserve full native coverage; no failing Windows job was removed.

## Explicitly outside acceptance

Real Mac installer/permission prompts/Terminal TCC attribution, Windows ARM64,
authenticated model execution, signing/notarization and a universal desktop-control
companion remain **unverified or unimplemented**. The Mac ZIP is experimental.
No model calls, real agent-home activation, OS grant changes or gateway restarts
were performed. Native parser/policy checks are not model-session tests.

OpenClaw uses the default local `.openclaw` layout on Linux/WSL; Mac source support
is not a hardware acceptance claim. Read [OPENCLAW.md](OPENCLAW.md) for exact scope.
OFF restores stored settings; it does not stop existing agents or undo their work.
