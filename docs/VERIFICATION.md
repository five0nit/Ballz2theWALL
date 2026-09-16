# Verification — 0.3.0a0.dev6 source candidate

**Automated candidate evidence exists; public-release and owner acceptance are
not complete.** Published downloads remain
[v0.2.0a2](https://github.com/five0nit/Ballz2theWALL/releases/tag/v0.2.0a2), whose
original verification page is preserved unchanged at
[VERIFICATION-0.2.0a2.md](VERIFICATION-0.2.0a2.md).

Machine-readable, publication-safe summary:
[release-readiness/public-summary.json](verification/release-readiness/public-summary.json).
Raw local logs can contain private paths and are not required public downloads.

Fresh repository/site checks are recorded separately in
[dev6-docs-update.json](verification/dev6-docs-update.json): source **917 passed /
4 skipped**, final bundled-skill/CLI/core/installer checks **60 passed**, a clean
rebuilt-wheel CLI round trip, and four local desktop/mobile/fallback browser cases.
No live owner acceptance was performed. The saved evidence below remains bound
to its original artifacts.

## Saved dev6 automated evidence

| Gate | Recorded result | Scope |
| --- | --- | --- |
| Source regression | **917 passed, 4 skipped** | Source candidate tested in the recorded run |
| Clean installed Python 3.11 wheel | **917 passed, 4 skipped** | Separate non-editable installed-wheel run |
| Native Windows installed-wheel scope | **241 passed, 1 skipped** | Selected Windows tests, not a duplicate full-suite claim |
| Native Windows scratch activation/OFF | **5 passed** | Scratch controller state; not existing authenticated-agent acceptance |
| Clean wheel with 640-digit integer policy | **198 passed** | Decimal/wire robustness scope |
| Non-elevated long jobs | **125 seconds on WSL and native Windows** | Completed with live output and disk-marker verification under a 120-second MCP client request timeout |
| Native Windows install/reinstall | **Passed in scratch** | Isolated paths; real profiles, PATH and shortcuts preserved |

These are separate runs, not an additive total of unique tests. Saved artifact
checks matched packaged source, wheel RECORD entries and the embedded wheel in
both installer ZIPs. Independent specification and quality reviews approved the
scoped Administrator-job lifecycle/integration work, not whole-product acceptance.
A scoped secret review reported no unresolved findings; it was not a new universal
scan of every historical file.

The saved test/artifact receipts are bound to their recorded candidate bytes.
Updating README or the bundled skill changes package inputs: future rebuilt
artifacts need their own hashes and applicable package checks. Do not attach the
old artifact checksums to a rebuilt wheel or claim its gates were rerun here.

## Owner and distribution gates still open

1. **Genuine Windows elevation:** owner-present UAC, observed same-user elevated
   helper, a harmless actual elevated job, cancellation/cleanup and OFF. Injected
   privilege detection in scratch tests does not satisfy this gate.
2. **Signed-in browser:** owner-approved session access preserving existing
   profiles/logins. A disposable browser is not an authenticated-browser test.
3. **Current authenticated agent:** dev6 startup in the selected existing agent,
   connected machine MCP, real tool call, ON/OFF revocation and exact config
   restoration. Historical dev3 authenticated success is not dev6 proof; Claude
   authenticated startup remains separately unverified.
4. **Normal consumer path:** test the exact candidate downloaded archive through
   first install, launcher, selected-agent connection and OFF. Scratch installer
   checks do not establish first-run OS prompts, ordinary shortcuts or consumer UX.
5. **Mac/platform acceptance:** physical Mac installer, Terminal TCC attribution,
   grant denial/retry and desktop access; Windows ARM64 is also unverified.
   Mac remains experimental.
6. **Distribution:** complete transitive license review and candidate artifact
   acceptance. Dependency metadata inventory alone is not legal clearance.
   Bundles remain unsigned/not notarized; signing and first-run OS acceptance are
   required before a frictionless consumer-distribution claim.

No firmware/bootloader implementation or verification is claimed. Windows
Administrator is not SYSTEM, kernel or firmware authority. OFF revokes managed
access; it does not undo completed task effects or revoke persistent OS grants.

## Historical evidence is not replaced

- **v0.2.0a2:** published native-runtime controller;
  [unchanged release verification](VERIFICATION-0.2.0a2.md).
- **Earlier development:** dev1 disposable native Windows desktop/browser and
  installer checks, dev3 command-job and authenticated-agent receipts, and dev5
  decimal-wire checks remain historical. They establish only their recorded scope
  and version, not final dev6 acceptance.
- **Older releases:** [0.2.0a1](VERIFICATION-0.2.0a1.md) and
  [0.1.1](VERIFICATION-0.1.1.md).

The documentation refresh does not perform model calls, real-home activation,
UAC approval, signed-in browser access, gateway restarts or after-hours owner
acceptance. It does not replace immutable historical receipts.

[Changelog](../CHANGELOG.md) · [Capabilities](CONSUMER-ACCESS.md) ·
[Command lifecycle](COMMAND-JOBS.md) · [Design](DESIGN.md)
