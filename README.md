# Ballz2theWALL

**Less asking. More doing. Actual permissions, not magic prompts.**

Owner-approved machine access for existing agents: native runtime settings,
command and file tools, desktop/browser control, and separately approved Windows
administration. Keep your existing agent, login and model; select one home and
use ON/OFF to manage Ballz access.

## Version status

| Version | What it means |
| --- | --- |
| **0.3.0a0.dev6 — current source** | Development source with machine MCP, desktop bridge, Windows helper and background jobs; no dev6 installer release. Automated evidence exists; owner-assisted and distribution acceptance remain pending. |
| **[v0.2.0a2 — published alpha downloads](https://github.com/five0nit/Ballz2theWALL/releases/tag/v0.2.0a2)** | Earlier native-runtime configuration controller and guided installers. These downloads do **not** contain the dev6 machine-control features. |

The platform ZIPs are unsigned; Mac installation remains experimental and has not
passed physical Mac acceptance. No PyPI publication is claimed. Download links
still select v0.2.0a2, not an implicitly upgraded development build.

[Info page](https://five0nit.github.io/Ballz2theWALL/) ·
[Changelog](CHANGELOG.md) · [Guided setup](docs/GUIDED-SETUP.md) ·
[Capabilities and limits](docs/CONSUMER-ACCESS.md) ·
[Verification](docs/VERIFICATION.md)

## What the current source adds

- **Machine MCP:** `ballz on` connects the selected runtime to the managed
  `ballz2thewall_machine` stdio server. Hermes and Codex receive native config
  bindings; Claude receives `--mcp-config` on matching managed launches only.
  OpenClaw support is limited to its validated local configuration.
- **Commands and files:** `machine_exec` runs explicit argument arrays in an
  explicit working directory; `machine_file` reads, writes, lists and stats paths
  using the launching account's filesystem rights.
- **Desktop, browser and applications:** tools from pinned **cua-driver 0.28.1**
  are discovered dynamically and exposed with a `desktop_` prefix. These use the
  runtime's own host desktop; WSL is not a bridge to the native Windows desktop.
- **Long-running jobs:** `machine_exec` with `background:true` returns a handle;
  `machine_job` lists, inspects output and cancels jobs in the same MCP session.
  `timeout:0` means no command deadline, not a persistent service. See
  [command jobs](docs/COMMAND-JOBS.md).
- **Windows Administrator helper:** an explicit owner-approved UAC prompt enables
  foreground and background administrative commands for that activation. Commands
  request it with `administrator:true`; they never trigger UAC implicitly or fall
  back silently to account rights. A pending approval can be cancelled and retried
  from the launcher.
- **Managed OFF:** revokes machine access before restoring saved configuration;
  connected Ballz servers close and managed commands receive cancellation. OFF
  does not stop the agent's other tools, undo completed work or revoke OS grants.

These are implemented source capabilities, not a claim of final consumer
acceptance. Genuine UAC/elevated-job cleanup, signed-in browser access, a fresh
dev6 authenticated-agent/OFF round trip and normal downloaded-install acceptance
remain open. Historical dev1 desktop/browser and dev3 authenticated-agent evidence
do not certify dev6. See the [current verification scope](docs/VERIFICATION.md).

## Install and connect

### Published alpha download

1. Download **v0.2.0a2**, extract the whole Windows or Mac Setup ZIP.
2. Double-click `Install-Windows.cmd` or `Install-Mac.command`.
3. Follow the dialogs; setup installs private Python. Existing agent installation
   and its own sign-in are prerequisites.
4. Select the intended agent, approve applicable OS settings and choose **Turn ON**.

The published alpha changes native runtime settings only. Its OFF restores saved
settings; close the agent to stop its running tools. It has no dev6 machine MCP or
Windows helper. Read its [historical verification](docs/VERIFICATION-0.2.0a2.md).

### Current source — development use

Python 3.11 or newer is required. From this reviewed checkout:

```bash
uv tool install .
ballz --version
ballz doctor hermes --home "$HOME/.hermes"
ballz machine check
ballz setup --check

# Guided setup; Linux/WSL uses terminal guidance.
ballz setup --gui
```

`doctor` checks native CLI capabilities, not login. `machine check` checks pinned
packages and driver startup, not OS permissions or signed-in browser access.
Installing with pip/uv or loading the skill alone does not activate an agent.

For an explicitly selected, already-configured home:

```bash
# Preview native runtime settings only; this is not a machine-binding dry run.
ballz plan hermes --home "$HOME/.hermes"

# Turn ON native settings and managed machine access for this home.
ballz on hermes --home "$HOME/.hermes"
ballz status
ballz run hermes --home "$HOME/.hermes" --cwd "$PWD" --interactive

# Revoke managed access and restore the original configuration.
ballz off
```

Use one state directory consistently if passing `--state-dir`. An older
runtime-only activation must be turned OFF before enabling machine access.
Restart the selected agent to load new bindings/tools; no live gateway is
restarted automatically. Prefer an immutable, locally verified dev6 wheel for
candidate deployment; an old v0.2.0a2 wheel does not install these features.

## Native runtimes

| Runtime | Native access mode | Current machine connection |
| --- | --- | --- |
| Hermes | `--yolo`; stored approvals disabled, local terminal backend, private/LAN URL allowance | `mcp_servers.ballz2thewall_machine` in selected `config.yaml` |
| OpenAI Codex | `--dangerously-bypass-approvals-and-sandbox`; `approval_policy = "never"`, `sandbox_mode = "danger-full-access"` | `mcp_servers.ballz2thewall_machine` in selected `config.toml` |
| Anthropic Claude Code | `--dangerously-skip-permissions`; `permissions.defaultMode = "bypassPermissions"`, native shell sandbox disabled | Inline `--mcp-config` on `ballz run` / launcher startup for the matching ON home; not `settings.json` or `~/.claude.json` |
| OpenClaw | Embedded `agent --local`; native tool/exec policy and separate host approvals, sandbox off | `mcp.servers.ballz2thewall_machine`; native schema/effective-policy validation required |

`openai` aliases `codex`; `anthropic` aliases `claude`. These are local agent CLI
adapters, not remote model API permission switches. Existing native deny rules,
hooks, organization policies, provider rules and OS protections remain relevant.
Administrator access is not SYSTEM, kernel, bootloader or firmware control.

OpenClaw is limited to the default `.openclaw` layout on Linux/WSL/macOS, not
native Windows, named profiles, remote gateways/nodes or per-agent runtime
overrides. Its policy contract targets **2026.6.1**; parser/discovery evidence is
not authenticated model/tool execution. [Adapter details](docs/ADAPTERS.md) ·
[OpenClaw policy contract](docs/OPENCLAW.md).

### Runtime-only operations

`apply` persists native runtime settings and returns a rollback receipt; it does
**not** create a managed machine activation. `run` does not persist settings or
turn machine access ON. For Claude, it adds the machine binding only when a
matching ON activation already exists.

```bash
ballz apply claude --home "$HOME/.claude"
ballz run codex --home "$HOME/.codex" --cwd "$PWD" --prompt-file task.txt
ballz run hermes --home "$HOME/.hermes" --cwd "$PWD" --prompt-file task.txt --dry-run
ballz rollback RECEIPT_ID
```

`--dry-run` resolves no secrets and makes no model call. Hermes launches require a
local terminal backend: `terminal.backend` takes precedence over legacy
`terminal.env_type`. The selected `--cwd` overrides stored messaging cwd. Explicit
Hermes roots are pinned with `--profile default`; named profile homes retain native
pinning without rewriting `active_profile`.

## Browser sessions and credentials

The managed desktop bridge is separate from these optional native browser routes:

- **Hermes:** `ballz browser-check http://127.0.0.1:9222`, then pass that existing
  endpoint with `--cdp` to `apply` or `run`. The check reads `/json/version` only;
  it does not list tabs, expose debugger WebSocket URLs or prove site login.
- **Claude:** `ballz run claude --home "$HOME/.claude" --cwd "$PWD" --interactive --chrome`
  selects the native Chrome extension. Installation/pairing and host support are
  separate prerequisites.
- **Codex:** the current managed MCP provides driver browser tools; `--cdp` is not
  a Codex adapter. Other browser MCP integrations remain independently configured.

Browser access depends on host permissions, browser state and the selected
integration. Chrome's default-profile debugging restrictions still apply. Ballz
does not extract saved passwords, decrypt Login Data/Local State, harvest cookie
databases, copy profiles or bypass OS unlock prompts.

Native agent logins stay in their own homes. A new empty home is not logged in.
Selected extra credentials can be resolved into the launched child's environment:

```bash
ballz run hermes --home "$HOME/.hermes" --cwd "$PWD" --prompt-file task.txt \
  --secret SERVICE_API_KEY=env:MY_SERVICE_API_KEY

ballz run codex --home "$HOME/.codex" --cwd "$PWD" --prompt-file task.txt \
  --inherit-secrets --secret SERVICE_API_KEY=op:op://Work/Service/api_key

# Optional OS keyring provider:
uv tool install '.[keyring]'
ballz run claude --home "$HOME/.claude" --cwd "$PWD" --prompt-file task.txt \
  --secret SERVICE_API_KEY=keyring:service/account
```

1Password needs an authenticated official `op` CLI. `--inherit-secrets` disables
Codex's default secret-name filter; explicit existing exclusion rules remain.
References contain no literal passwords. Ballz omits resolved values from its
receipts, but launched agents, commands and their logs can expose values they use.

## Local processes, dependencies and privacy

Ballz requires no hosted Ballz account or scheduler. The current package includes
**mcp 1.30.0** and **cua-driver 0.28.1** as required dependencies. While connected,
it runs a local stdio MCP server and an owned driver process using
`mcp --direct --no-overlay`, not the user's shared Cua daemon. The optional Windows
helper is ephemeral and uses an authenticated loopback listener; it is not an
installed always-on service. Background jobs are session-owned subprocesses.

Ballz's controller does not add a product-telemetry sender. **This is not a
whole-stack no-telemetry claim:** Cua has content-free product telemetry enabled
by default and separate `cua-driver telemetry` controls. Agent/provider logging,
dependency networking and first-install downloads have their own behavior. Full
transitive license review and distribution acceptance are still pending.

## OFF, rollback and receipts

For managed `on`, use **`ballz off`**, not plain rollback. OFF first changes the
activation to `stopping`, denying old/new calls with that identity, then stops the
helper and restores original configuration bytes or absence. Drift, missing
receipts or cleanup failure remain visible; resolve the conflict and retry.
Cancellation/transport cleanup is asynchronous, not proof all children are reaped
when OFF returns. Escaped/detached descendants are not guaranteed terminated.

OFF does not revoke macOS grants, undo completed commands/files/browser actions,
stop the agent process, or disable its unrelated native tools. Close the agent
window to stop that session; existing gateway processes are not automatically
reconfigured or restarted.

Default state is `${XDG_STATE_HOME:-~/.local/state}/ballz2thewall` on POSIX and
`%LOCALAPPDATA%/Ballz2theWALL/state` on Windows. The store uses hashes, locking and
original-byte backups; Windows additionally uses protected owner ACLs, byte-range
locks, reparse/hardlink rejection and write-through replacement. OpenClaw's
two-file journal provides recoverability, not filesystem-wide atomicity.

Rollback refuses newer edits rather than overwriting them. Backups may contain
pre-existing secrets: keep state private, local and outside version control. This
is an operator recovery log, not an adversarially signed audit service.

## Skill and development

```bash
ballz skill
ballz skill --dest "$HOME/.hermes/skills"
# Or choose the other host's documented skills root explicitly.
ballz skill --dest "$HOME/.claude/skills"
```

Skill installation writes only `ballz2thewall/SKILL.md` and returns a rollback
receipt. Loading it does not activate access.

```bash
uv venv .venv
uv pip install --python .venv/bin/python -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests scripts
.venv/bin/python -m build
```

[Design](docs/DESIGN.md) · [Adapters](docs/ADAPTERS.md) ·
[Command jobs](docs/COMMAND-JOBS.md) · [Current evidence](docs/VERIFICATION.md) ·
[Historical v0.2.0a2 evidence](docs/VERIFICATION-0.2.0a2.md) ·
[Changelog](CHANGELOG.md)

MIT licensed. Unsigned alpha/development software, not universal unrestricted access.
