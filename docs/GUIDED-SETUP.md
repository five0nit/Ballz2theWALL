# Guided setup — 0.2.0a2 unsigned alpha

## User path

Extract the platform ZIP → double-click its installer → follow dialogs → approve
OS requests/settings → Turn ON → Start agent. No terminal commands, Python, Git,
Homebrew, MCP fields or helper configuration required for this installation flow.
One discovered compatible agent is selected automatically. With several profiles,
choose the one to change. Existing agent installation and its own login remain
prerequisites; Ballz never reads or migrates authentication.

## macOS 11 and newer

`Install-Mac.command` runs in Apple's Terminal and installs private Python 3.11
with pinned/checksummed uv. It creates `~/Applications/Ballz2theWALL.command`.
Use that launcher for setup and agent startup, retaining Terminal as the stable
responsible application. No temporary Python helper is presented as a separate
signed permission owner.

- Accessibility: `AXIsProcessTrustedWithOptions` requests access; guidance opens
  `Privacy_Accessibility` and asks the user to enable **Terminal**.
- Screen Recording: `CGRequestScreenCaptureAccess` requests access; guidance opens
  `Privacy_ScreenCapture`. macOS can require quitting/reopening Terminal.
- Full Disk Access: no grant API exists. Open `Privacy_AllFiles`; explain how to
  add/enable `/System/Applications/Utilities/Terminal.app`. Read-only opening of
  the user's TCC database tests access without reading its contents. Missing
  probe location is **unknown**, not permission granted. In that case a user's
  manual confirmation is recorded explicitly, never converted to verified access.
- Automation: a read-only Finder version Apple Event triggers Finder consent.
  Other apps request their own consent when used. No blanket preapproval.

Check Again re-reads available status; Not Now cancels without activating a
profile. Existing grants skip redundant requests. This covers Terminal-launched
processes, not LaunchAgents/daemons, SSH agents or a future companion identity.

**Native Mac runtime and privacy attribution acceptance is pending.** Bash syntax,
request routing and state behavior are tested on the build host; that does not
prove prompts, System Settings targets or TCC inheritance on real macOS. These
scripts are not a signed/notarized application. Gatekeeper policy is not removed.

## Windows

`Install-Windows.cmd` opens the PowerShell/WinForms installer. Installation is per
user, under `%LOCALAPPDATA%/Ballz2theWALL`; no system PATH edits or administrator
request. It downloads SHA-256-pinned uv and managed Python, validates the bundled
wheel, installs it, verifies the installed entrypoint and creates a verified
Start Menu shortcut. Failure details remain in logs; the success-only `runtime/install-receipt.json` is written after successful installation and verification.

The setup wizard checks native interactive-session and elevation state. Ordinary
Windows desktop/terminal access does not have Mac-style permission toggles. UAC
is still required for separately elevated actions; this build does not provision
a persistent administrative helper or promise lasting Administrator access.

Testing flags: `-NonInteractive -NoLaunch -NoShortcut -InstallRoot PATH` exercise
installation in a scratch directory without presenting dialogs or changing real
shortcuts. They do not grant permissions or activate profiles.

## OpenClaw scope

OpenClaw is available on Linux/WSL and macOS with a standard `.openclaw` home.
Its native embedded terminal prompt loop is launched without starting a gateway.
Windows users with OpenClaw inside WSL must install Ballz inside WSL too; the
native Windows installer does not bridge into WSL. Named profiles, remote/node
execution and explicit per-agent runtime overrides are outside this alpha.
See [the adapter contract](OPENCLAW.md) for the exact supported settings.

## ON and OFF

ON writes only the chosen runtime configuration after an explicit action. A
write-ahead activation journal and isolated original-byte receipt allow restart
and interrupted-operation recovery. OFF restores original bytes (or absence);
newer edits and corrupted/missing receipts stop restoration instead of overwriting.

Close the agent window first. OFF changes stored runtime configuration; it does
not terminate existing processes, revoke OS permissions or undo completed work.
No desktop-control server, arbitrary-agent bridge or privileged daemon is bundled.
The underlying runtime still needs its own configured tools.

CLI equivalents:

```text
ballz setup --gui
ballz setup --check
ballz on hermes --home /absolute/selected/home
ballz off
```

Direct `pip`/`uv tool` installation and `ballz skill --dest` deliberately have no
hidden post-install execution. Use the setup command or platform installer to
request permissions. Merely loading SKILL.md never triggers OS prompts.

## Build and acceptance

```text
python -m build --wheel
python scripts/build_installers.py --wheel dist/ballz2thewall-0.2.0a1-py3-none-any.whl --output dist
```

Bundled wheel and uv archives are checksum-verified; this is not code signing.
First installation needs network access for managed Python and package dependencies.
Both x64 and ARM64 bootstrap assets are pinned; only native Windows x64 has been
executed here. Mac Intel/Apple Silicon and Windows ARM64 still require acceptance.

Physical Mac acceptance: fresh install; observe correct Terminal identity on each
request; deny/retry each grant; restart Terminal; verify Accessibility and screen
access; verify protected-file access; approve Finder event; launch the selected
agent in this same lineage; restore original configuration using OFF. Never mark
these gates complete from mocked APIs or Windows tests.
