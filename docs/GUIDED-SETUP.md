# Guided setup — current source and published alpha

**Current source: 0.3.0a0.dev6. Published downloads: v0.2.0a2.** The downloadable
alpha configures native runtime settings; it does not include dev6 machine MCP,
background jobs or the Windows Administrator helper. Dev6 owner acceptance is
pending. [Verification](VERIFICATION.md) · [Capabilities](CONSUMER-ACCESS.md).

## User path

Extract the whole platform ZIP → double-click its installer → follow dialogs →
approve applicable OS requests/settings → Turn ON → Start agent. Existing agent
installation and its own sign-in are prerequisites. Ballz does not migrate login
stores or authenticate an empty agent home. With several compatible homes, choose
exactly the one to change.

The installer manages its private Python environment. In dev6 it also installs the
machine dependencies and checks package/driver readiness before reporting success;
MCP registration belongs to ON, not to a separate user configuration project.
Package readiness does not establish OS permission or authenticated-agent success.

For the published alpha, use the [v0.2.0a2 release](https://github.com/five0nit/Ballz2theWALL/releases/tag/v0.2.0a2).
Do not expect these downloads to upgrade themselves to development source.

## Windows

`Install-Windows.cmd` opens the PowerShell/WinForms installer. Installation is per
user under `%LOCALAPPDATA%/Ballz2theWALL`; it does not require an Administrator
install or edit system PATH. Pinned uv bootstraps private Python; the installer
validates the bundled wheel, installed entrypoint and machine-readiness result,
then creates a verified Start Menu shortcut. A successful install writes
`runtime/install-receipt.json`; failures remain in logs.

Ordinary desktop, file and command tools use the launching account's rights.
Dev6 has a separate **owner-approved UAC flow** for the ephemeral Administrator
helper. It is activation-bound, not an always-on privileged service. Approve UAC
personally. If approval remains pending, the launcher can cancel/retry it; retry
revokes the old reservation before asking again. Commands must explicitly request
`administrator:true` and fail when the helper is unavailable; they do not silently
fall back to account rights or trigger UAC themselves.

Real UAC, elevated work and cleanup are still owner-acceptance gates. The earlier
v0.2.0a2 download has no such helper. Neither version promises SYSTEM, kernel,
bootloader or firmware access.

`-NonInteractive -NoLaunch -NoShortcut -InstallRoot PATH` exercises installer logic
in a scratch directory. It does not grant permissions, activate profiles or prove
the ordinary consumer download/first-launch path.

## macOS 11 and newer — experimental

`Install-Mac.command` runs in Apple's Terminal, bootstraps private Python and creates
`~/Applications/Ballz2theWALL.command`. Keep Terminal as the responsible application
when launching setup and the selected agent. These scripts are unsigned and not
notarized; they do not remove Gatekeeper policy.

- **Accessibility:** setup requests access and opens its System Settings panel;
  enable the intended Terminal application personally.
- **Screen Recording:** setup requests access and opens its panel. macOS may require
  quitting and reopening Terminal.
- **Full Disk Access:** no grant API exists. Add Terminal in System Settings. A
  missing read-only probe location is unknown, not permission granted; manual
  confirmation is recorded as manual, not verified access.
- **Automation:** the Finder version Apple Event requests Finder consent. Other
  applications request their own consent when used; there is no blanket grant.

Check Again rereads status. Not Now leaves the profile inactive. This guidance
concerns Terminal-launched processes, not LaunchAgents, SSH or a future app identity.
Physical Mac install, TCC attribution, desktop operation and restoration remain
unverified. Source compatibility and mocked checks do not close those gates.

## Linux, WSL and OpenClaw

Linux/WSL uses terminal guidance rather than a native GUI installer. The managed
desktop bridge acts on the runtime host; WSL is not a bridge into the native Windows
desktop. Install and launch on the host whose desktop is intended.

OpenClaw supports a default `.openclaw` layout on Linux/WSL/macOS. Its embedded
terminal loop does not start a gateway. Native Windows, named profiles and remote
nodes are outside the contract. Dev6 registers local machine MCP subject to native
schema/effective-policy validation. [OpenClaw details](OPENCLAW.md).

## ON, launch and OFF in dev6

ON creates a managed activation for the selected home and writes native settings
plus the applicable machine binding. Hermes/Codex/OpenClaw load that binding from
configuration; Claude Code receives inline MCP configuration only on matching
managed launches. Restart the selected agent to load new tools; Ballz does not
restart existing gateways automatically. `apply` is a separate runtime-settings
transaction and does not turn machine access ON.

```text
ballz --version
ballz setup --check
ballz machine check
ballz setup --gui
ballz on hermes --home /absolute/selected/home
ballz status
ballz run hermes --home /absolute/selected/home --cwd /absolute/workspace --interactive
ballz off
```

Use the same `--state-dir` throughout if choosing a custom store. Turn an older
runtime-only activation OFF before enabling machine access. `machine check` checks
packages and driver startup, not OS grants or browser login.

OFF revokes managed access before restoring saved configuration bytes or absence.
Connected Ballz servers close; session-owned commands receive cancellation and
owned driver/helper cleanup follows. Cancellation is asynchronous: OFF returning
is not proof every child has been reaped. Detached descendants are not guaranteed
terminated. Drift, damaged receipts and cleanup failures remain visible for retry.

OFF does **not** undo completed work, revoke OS grants, kill the agent's unrelated
tools or promise to stop every machine process. Close the agent window to stop that
session. The older v0.2.0a2 OFF restores runtime settings only.

Installing via pip/uv or loading `SKILL.md` has no hidden activation or OS-approval
side effects. Ballz has no hosted account; its required Cua dependency has separate
telemetry controls. [Dependency/privacy scope](CONSUMER-ACCESS.md).

## Build and acceptance

From the reviewed development checkout, with build dependencies installed:

```text
python -m build --wheel
python scripts/build_installers.py --wheel dist/ballz2thewall-0.3.0a0.dev6-py3-none-any.whl --output dist
```

Checksums establish integrity, not signing. First installation needs network access
for private Python and dependencies. x64/ARM64 bootstrap assets are pinned; native
Windows x64 scratch installation evidence does not prove Windows ARM64 or physical
Mac acceptance. A rebuilt wheel needs its own installation and acceptance receipts;
older dev6 artifact hashes do not automatically certify it.

Before release: real UAC/elevated-job cleanup; signed-in browser session preservation;
final-candidate authenticated agent/tool/OFF restoration; normal downloaded install,
first launch and shortcuts; full dependency/license review; then owner publication
approval. Mac remains experimental until physical acceptance passes. No new package
release is implied by publishing source or updating this guide.
