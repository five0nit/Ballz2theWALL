# Consumer machine access — unpublished development

Version: **0.3.0a0.dev6** candidate, not yet release-approved. Published **0.2.0a2** assets remain unchanged.
Target: maximum owner-approved practical machine control through existing agents,
not a new model harness or a claim that every OS/provider boundary disappears.

## Implemented locally

- `ballz on` enables native runtime access settings and the machine MCP binding in
  the selected home only. Existing other homes, logins, models and channels stay intact.
- Hermes: `mcp_servers.ballz2thewall_machine` in `config.yaml`.
- Codex: `mcp_servers.ballz2thewall_machine` in `config.toml`.
- OpenClaw 2026.6.1: `mcp.servers.ballz2thewall_machine` in `openclaw.json`.
- Claude Code: inline `--mcp-config` on **managed launches only**; not placed in
  `settings.json` or the separate global `~/.claude.json`. No `--strict-mcp-config`.
- `machine_exec`: command execution in an explicit working directory using current
  account rights, or the separately approved native Windows helper when `administrator:true`.
- `machine_file`: read/write/list/stat within filesystem rights granted by the OS.
  The convenience tool has a 256 KiB file-read/write bound; arbitrary files can be
  processed through command execution instead.
- `machine_status`: activation and approved helper status.
- `machine_exec` with `background:true`: start an account-rights or separately approved Windows Administrator command without
  holding an MCP request open. `machine_job` lists, inspects live output or cancels
  commands belonging to the same connected MCP session. No new service or dependency.
  See [command-job contract](COMMAND-JOBS.md) for lifecycle and output details.
- Desktop/browser/application tools proxied from **cua-driver 0.28.1** over local
  stdio. Driver authorization uses documented `CUA_DRIVER_PERMISSION_MODE=unrestricted`
  and `CUA_DRIVER_DANGEROUSLY_BYPASS_APPROVALS=1`; OS permission prompts still apply.
  This is not evidence that every listed tool works on every host. Cua sends
  content-free product telemetry by default; its own `cua-driver telemetry`
  controls apply separately from Ballz's behavior.
- Windows setup offers **Approve Administrator access** or account-only mode.
  Only an explicit approval launches UAC. The helper is activation-bound, ephemeral
  and authenticated on loopback; it is not an installed always-on service.
  A timed-out approval is shown as pending. Reopen the launcher, dismiss the old
  Windows prompt and choose **Cancel pending approval and retry** to revoke that
  reservation before a new prompt. Keeping the pending approval does not relaunch UAC.

## OFF semantics

OFF revokes the activation before restoring exact saved configuration bytes.
Already-connected managed MCP servers stop; future calls with the old identity fail.
Ordinary and approved-helper in-flight managed commands are cancelled. Configuration drift or helper
cleanup failure leaves a visible `stopping` state, not a false successful OFF.
Direct desktop CLI discovery/calls also watch activation during connection,
initialization and execution; revocation cancels the call and closes its owned
stdio transport. Expected administrative failures return structured errors and
a controlled nonzero CLI exit, rather than escaping as tracebacks.
Retry after addressing the reported conflict. OFF does not undo completed actions,
revoke persistent OS grants, terminate the agent itself, or guarantee termination
of detached/escaped descendants. Administrator helper reports this distinction.

## Actual limits, not marketing claims

- OS account grants still apply. Windows UAC approval is separate from native agent
  approval flags. Windows Administrator is not SYSTEM, kernel or firmware access.
- Native elevated helper is Windows-only. There is no equivalent macOS/Linux root
  helper implemented by this change. Mac TCC/Terminal acceptance remains pending.
- Standard and administrative commands accept `timeout:0` (no command deadline)
  and positive integer deadlines without a 600-second cap. Unlimited administrative
  commands still stop on OFF; their response transport has no separate command deadline.
  Ballz configures 120-second tool-call timeouts for its Hermes, Codex and OpenClaw
  bindings. Claude's inline binding sets no timeout; its client deadline remains
  runtime-controlled. For long ordinary or approved Administrator
  commands, `background:true` returns a handle immediately; inspect it with short
  `machine_job` requests. This does not extend foreground or desktop-tool
  transport deadlines, or keep work alive after MCP disconnect/restart.
- Managed policy, provider rules, quotas, context limits, physical hardware boundaries,
  signed-in browser availability and externally denied tools are not removed.
- Cua calls use the desktop on the runtime's host. WSL is not a native Windows
  desktop bridge. Native Windows tests use a separate Windows Python installation.
- No bootloader, firmware or host protection changes were made or exercised.

## Verification and unresolved acceptance

Baseline dev1 results: `verification/consumer-access/gates.json`. The following
desktop/browser/installer acceptance is historical **dev1** evidence, not a claim
that every native gate was repeated on dev6. Dev3 command-job evidence is kept
separately under `verification/command-jobs/`; dev5 decimal-wire evidence is under
`verification/decimal-wire/`. Current candidate evidence belongs under
`verification/release-readiness/`; only explicitly completed gates count.

Executed: source and fresh installed-wheel regression; real stdio initialize,
tools/list, command/file operations and OFF blocking; native Hermes connection,
Codex parsing, OpenClaw parsing/discovery; native Windows scratch package tests.

The installer continuation also exercised clean native Windows installation,
reinstallation and source installation inside a disposable path containing spaces
and `&`, without real Start-menu shortcuts or changes to PATH/agent profiles.
The installed runtime reports pinned `cua-driver 0.28.1` and `mcp 1.30.0` ready.
Readiness is package/import/startup evidence, not completed browser or OS consent.

Real native Windows desktop interaction passed through that installed MCP bridge:
launch a disposable WinForms fixture, capture its UI, background-set its textbox,
invoke its Save button, and verify the exact saved value on screen and on disk.
OFF cancelled an in-flight command and rejected subsequent file/desktop calls.
The fixture was closed with its owned transport; no personal app was targeted.

**Native disposable-browser round-trip passed on the final installed wheel.**
Earlier probes redirected Windows `USERPROFILE` and failed before DevTools startup.
A bounded comparison reproduced failure with that override and successful startup
with the native `USERPROFILE`, keeping browser data isolated using
`CUA_DRIVER_BROWSER_PROFILE_ROOT`. No product-code change was required.
The installed MCP bridge then prepared a new Chrome profile, bound its observed PID
and native window, navigated to a loopback fixture, typed a unique value, clicked Save,
and returned screenshots matching the exact persisted server-side value. OFF rejected
another browser navigation. Personal profiles/logins were not used; signed-in-session
acceptance remains separate. See `verification/consumer-access/browser-native/`.

The exact final Windows ZIP also passed clean installation and reinstallation into
a disposable path containing spaces and `&`. Both receipts match the final wheel
SHA256 and report machine runtime `ready`; installed package smoke passed.
See `verification/consumer-access/final-wheel-native/` for the earlier bundle.

The subsequent installer review reproduced a P2 evidence-validation defect:
validators accepted missing/false package `importable` and an unrelated driver
version. Both installers and the native receipt assertion now require Boolean
`true` for each package and the exact `cua-driver 0.28.1` version string.
The valid fixture matches the producer; negative cases exercise missing values,
false values, wrong types and mismatched versions through the production validators.
After the fix, source and installed-wheel suites each passed **792 tests, 4 skipped**.
Rebuilt Windows ZIP clean installation, reinstallation, strict receipt readback
and installed-package smoke all passed in a new disposable native Windows path.
All 20 installed package files match the unchanged wheel and source. Mac validator
execution and ZIP integrity passed; physical Mac installation remains untested.
Current evidence: `verification/consumer-access/readiness-review/`.
Independent closure review `deleg_1f3ad351` **APPROVED** the scoped P2 repair:
**73 tests passed**, including rejection of all 24 malformed evidence cases across
the Windows validator, Mac validator and receipt assertion. The parent verified
all six reviewed file SHA-256 values against the unchanged workspace. Original
`REQUEST_CHANGES` evidence remains recorded; this approval does not claim the
remaining owner-assisted, platform or release acceptance gates.

Still required before consumer release:

1. Owner-approved native Windows UAC → actual elevated harmless operation → OFF.
2. Verify owner-approved signed-in browser-session access (disposable browser interaction passed).
3. Selected existing-agent authenticated startup showing connected MCP server and a real tool call;
   Claude authenticated startup remains separately unverified.
4. Physical Mac installation, permissions, Terminal attribution and desktop acceptance.
5. Dependency/license distribution, signing and final release-artifact acceptance.

No new release, public website deployment, live-profile activation, model execution
or OS permission change is claimed by this development receipt.

## Developer verification

```bash
.venv/bin/pytest -q
.venv/bin/ruff check src tests scripts/machine_native_smoke.py
python -m build --wheel
# Install the wheel into a new environment; -I requires a real installation.
/path/to/clean/python -I -m pytest -q -o pythonpath=
/path/to/clean/python -I scripts/package_smoke.py
/path/to/clean/python -I scripts/machine_native_smoke.py /tmp/machine-native-receipt.json
```

`machine_native_smoke.py` uses temporary homes and native discovery only, not models.
It does not verify Claude authenticated startup or configuration acceptance.
No credentials are copied into scratch profiles.

Reuse evidence: `discovery/CONSUMER-ACCESS.json`; original bounded Brief2Ship run
`/tmp/brief2ship-preflight-ballz-consumer-access-20260915`.
