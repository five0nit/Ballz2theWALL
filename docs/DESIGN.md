# Design and acceptance — 0.3.0a0.dev6 source

## Objective

Connect an existing agent to owner-approved machine access with one managed ON/OFF
lifecycle. Native approval flags alone are not the product: current source adds
command/file tools, a managed desktop/browser driver, session-owned command jobs
and a separately approved Windows Administrator helper.

The skill explains operation; the CLI implements it; native adapters bind the
selected home; private receipts preserve recovery data. Current source is distinct
from the v0.2.0a2 published installers. See [verification](VERIFICATION.md).

## Components

- `adapters.py`, `config.py`, `openclaw_runtime.py`: native settings, home/launch
  contracts, strict parsing and scoped OpenClaw policy validation.
- `store.py`: locking, original-byte backups, hash-bound rollback, recoverable
  multi-file transactions and native Windows ACL/replacement safeguards.
- `onboarding.py`: discovery, platform setup, activation journal, Windows approval,
  ON/OFF, restoration and interrupted-operation recovery.
- `machine_bindings.py`: selected-runtime MCP envelopes; Claude uses inline launch
  configuration instead of an unrelated global settings file.
- `machine.py`: activation-bound stdio MCP, command/file/status/job tools and dynamic
  `desktop_` tools from pinned cua-driver through an owned direct-mode process.
- `machine_jobs.py`: bounded output, background job lifecycle and cancellation.
- `admin.py`, `admin_jobs.py`: explicitly approved Windows helper, authenticated
  loopback transport and administrative job lifecycle; no persistent service.
- `machine_check.py`, `wire_json.py`: pinned dependency readiness and strict wire
  JSON handling. Readiness is not live OS/browser acceptance.
- `doctor.py`, `browser.py`: native help/version checks and explicit CDP metadata
  probing, not authentication or private-browser-profile inspection.
- `credentials.py`: selected env/1Password/optional keyring references for a child,
  without copying native login stores.
- `cli.py`, bundled `skill/SKILL.md`, installers: operator interface, launch,
  dependency wiring and instructions; no hidden activation merely from installation.

## Lifecycle and security boundaries

1. Select one explicit home and local state store. Native `plan` previews runtime
   settings only; `apply` is a runtime-settings transaction, not machine activation.
2. ON validates prerequisites, journals the activation and writes native settings
   plus the appropriate managed binding. Existing namesake MCP entries are not
   overwritten silently. Native validation failures compensate changes.
3. A connected machine server validates the activation identity. Windows admin
   requires a separate owner-approved helper and an explicit administrative call.
4. Long commands can run as background jobs in that MCP session. `timeout:0` removes
   a command deadline, not the client MCP request timeout or session ownership.
5. OFF first makes the activation non-active, denying old/new managed calls, then
   cleans up the helper and restores original configuration. Servers close and
   command cancellation follows asynchronously. Failed restoration remains visible.

OFF is not an undo of completed operations or a machine-wide kill switch. It does
not revoke OS grants, stop unrelated agent tools, or guarantee termination of
escaped/detached descendants. Native OS and organization/provider boundaries remain.

## Acceptance dimensions

- Configuration preserves unrelated settings and restores exact bytes/mode or
  original absence. Reapply, drift, corrupt backups and interrupted recovery have
  explicit behavior; newer edits are not overwritten to manufacture success.
- MCP activation, tool discovery, commands/files, job output/cancellation and OFF
  revocation are separate from an authenticated native-agent round trip.
- Package importability, pinned driver version and installed CLI behavior are
  separate from actual desktop/browser functionality or OS permission approval.
- Real Windows UAC/elevated work, signed-in browser preservation, final-candidate
  authenticated execution and normal consumer installation require their own receipts.
- Physical Mac installation, TCC attribution, desktop operation and restoration
  cannot be inferred from mocks, Linux or native Windows subsets.
- Source, installed-wheel, native OS, historical agent and newly built artifact
  evidence must retain their actual version/hash/scope. Publishing docs is not release
  approval. Full license/telemetry/distribution review remains a separate gate.

[Current evidence and open gates](VERIFICATION.md) · [Tool contract](CONSUMER-ACCESS.md)

## Constraints and non-goals

Windows state uses owner ACLs, byte-range locks, reparse/hardlink rejection and
write-through replacement. POSIX uses its own lock/atomic-replacement path. Other
native editors do not honor Ballz locks and can race the final check. OpenClaw's
journal provides recoverable two-file updates, not filesystem-wide atomicity.

Backups can contain existing credentials; keep them private and outside Git.
Receipts are trusted local recovery data, not a signed adversarial audit ledger.
Provider logging, dependency networking and Cua telemetry remain distinct from
Ballz controller behavior; no whole-stack no-telemetry claim is made.

No credential harvesting, browser profile copying, OS protection bypass, hidden
persistence, automatic gateway rollout or implicit public release. Owner-approved
Windows Administrator access is implemented; SYSTEM/kernel/bootloader/firmware
control is not. The desktop runs on the runtime host, not across WSL/Windows by
assumption. Mac support remains experimental pending physical acceptance.
