---
name: ballz2thewall
description: Use when enabling owner-approved agent machine access. Configure explicit runtime homes, manage ON/OFF and command jobs, and preserve native authentication and rollback receipts.
license: MIT
metadata:
  version: 0.3.0a0.dev6
  platforms: [linux, macos, windows, wsl]
---

# Ballz2theWALL

**Less asking. More doing. Actual permissions, not magic prompts.**

This skill describes **0.3.0a0.dev6 development source**. Published **v0.2.0a2**
installers contain native runtime settings only, not the dev6 machine bridge,
background jobs or Windows helper. Final live owner/distribution acceptance is
pending. Loading this skill never activates access or requests OS permission.

## Operator workflow

1. Check `ballz --version`. If absent, install the reviewed repository or an
   explicitly supplied immutable wheel; do not assume a PyPI release exists.
2. Run `ballz doctor`, `ballz machine check` and `ballz setup --check`. These check
   CLI/package/driver readiness, not model login, signed-in browser access or
   genuine OS approval.
3. Select the exact intended home. Respect `HERMES_HOME`, `CODEX_HOME` and
   `CLAUDE_CONFIG_DIR`; another profile is not an implicit target. Keep one state
   directory throughout the workflow.
4. Preview native settings with `ballz plan hermes --home /absolute/runtime/home`.
   This is not a preview of the additional machine-binding transaction.
5. For approved managed access, use `ballz on hermes --home /absolute/runtime/home`
   or `ballz setup --gui`. ON creates the activation and applicable MCP binding.
   Resolve existing runtime-only activation with OFF before enabling machine access.
6. Launch the selected existing agent with
   `ballz run hermes --home /absolute/runtime/home --cwd /absolute/workspace --interactive`.
   This requires a TTY. `--prompt-file task.txt` supports a bounded one-shot task;
   `--dry-run` resolves no credentials and makes no model call.
7. Inspect `ballz status`; finish with **`ballz off`**. Do not substitute plain
   receipt rollback for revoking a managed activation. Retain receipts and resolve
   drift or cleanup failures rather than overwriting later edits.

Restart only the selected agent when needed to load new bindings. Existing live
gateways are not restarted automatically; obtain separate approval before doing so.
Use `codex`/`openai`, `claude`/`anthropic`, `hermes` or scoped local `openclaw`.
These are native agent adapters, not remote provider permission switches.

## Managed capabilities

- `machine_status`: inspect the current activation and capability state.
- `machine_exec`: explicit command argument array and working directory, using
  the launching account's rights unless approved Windows administration is requested.
- `machine_file`: bounded read/write/list/stat operations under current OS rights.
- `machine_job`: session-owned background command status, output and cancellation.
- Dynamic `desktop_` tools: desktop/browser/application operations from pinned
  **cua-driver 0.28.1**, exposed through local stdio with **mcp 1.30.0**.

For long commands use `background:true`, keep the returned handle and poll through
`machine_job`. `timeout:0` removes the command deadline; it does not remove an MCP
client timeout or make a job survive session teardown. Output is bounded. Do not
claim cancellation completed merely because a request was accepted.

Windows Administrator commands require a separately owner-approved, activation-bound
UAC helper and `administrator:true`. Missing approval fails visibly; commands never
silently downgrade or prompt for UAC themselves. Pending approval can be cancelled
and retried from setup. No always-on privileged service is installed. Administrator
is not SYSTEM, kernel, bootloader or firmware access.

Desktop tools run on the runtime's host. WSL is not a native Windows desktop bridge.
Signed-in browser access and physical Mac permission attribution remain separate
acceptance gates, not consequences of successfully importing the driver.

## Runtime bindings

- Hermes/Codex: selected-home `mcp_servers.ballz2thewall_machine` registration.
- Claude Code: inline `--mcp-config` only on a managed launch for the matching ON
  home; no MCP write into `settings.json` or unrelated `~/.claude.json`.
- OpenClaw: `mcp.servers.ballz2thewall_machine`, subject to native schema and
  effective-policy validation. Default `.openclaw` layout on Linux/WSL/macOS only;
  no native Windows, named profiles or remote nodes/gateways. The terminal wrapper
  calls `agent --local` without starting a gateway. Native `--message` puts prompt
  text in child argv; dry-run redacts it. Configured workspace rules remain native.

`ballz apply AGENT --home PATH` persists **native settings only**, returning a
receipt for `ballz rollback RECEIPT_ID`. `run` itself does not persist settings or
activate machine access. With a custom `--state-dir`, repeat it for every operation.
Explicit Hermes roots are pinned against sticky profile selection; backend precedence
honors `terminal.backend` before legacy `terminal.env_type`. Selected `--cwd` takes
precedence over stored messaging cwd.

## OFF and restoration

OFF marks the activation non-active before restoring saved config bytes or absence.
Old/new managed calls fail; connected servers close and managed commands receive
asynchronous cancellation. The owned driver/helper is part of cleanup. Drift,
missing/corrupt receipts or incomplete cleanup remain visible and can require retry.

OFF does not undo completed files/commands/browser actions, revoke OS grants, stop
the agent's unrelated tools or guarantee termination of detached descendants. Close
the agent window to stop that session. The older alpha's OFF restores runtime settings
only. Keep backups private: they can contain pre-existing config credentials.

## Browser, credentials and dependency privacy

- Hermes native CDP route: pass an explicitly approved existing endpoint with
  `--cdp http://127.0.0.1:9222`; `ballz browser-check` probes `/json/version` only.
- Claude native Chrome route: `ballz run claude ... --chrome`; extension pairing,
  installed prerequisites and host support are independent of the managed driver.
- Codex has no `--cdp` adapter; managed driver browser tools are available through MCP.
- Native logins stay in their own homes. Never copy login stores or infer an empty
  home is authenticated. No password/cookie database extraction or OS-unlock bypass.
- Selected child credentials use references such as `--secret API_KEY=env:MY_API_KEY`,
  `--secret API_KEY=op:op://Vault/Item/field` or
  `--secret API_KEY=keyring:service/account`. 1Password requires its authenticated
  official CLI; keyring needs the optional extra. Never put literal secrets in argv.
- Codex `--inherit-secrets` changes its default secret-name filter; existing explicit
  exclusions remain. Ballz receipts omit resolved values; child tools and logs can
  still expose values they use.

Ballz requires no hosted account. While connected, its local MCP server owns a
`cua-driver mcp --direct --no-overlay` process, not the user's shared daemon.
Cua has separate default-on telemetry and `cua-driver telemetry` controls; do not
claim the full stack is telemetry-free. Agent/provider logging, networking and
transitive licensing have their own boundaries.

## Verify honestly

Report configuration write, parser success, connection, authenticated tool execution,
OS approval, browser preservation, OFF and package provenance separately. Historical
dev3 agent success does not certify dev6. Windows mocks/scratch installs do not certify
real UAC or a normal downloaded first launch. Mac remains experimental until tested
on physical hardware. Automated counts are not owner acceptance.

Provider rules, native deny policies and OS protections remain relevant. No automatic
machine-wide rollout, hidden persistence, profile scraping or OS-protection changes.
Install this skill only into an explicitly selected root with
`ballz skill --dest /absolute/skills/root`; installation itself grants no access.
