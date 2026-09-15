# Ballz2theWALL

**Less asking. More doing. Actual permissions, not magic prompts.**

A local-first skill + CLI that puts agent runtimes into their native full-access
modes. Hermes first. OpenAI Codex and Anthropic Claude Code included.

**Status: 0.2.0a1 local alpha.** Guided Windows and Mac installation included.
Windows clean installation and native transactions tested. Mac installer/permission
flow implemented but not yet tested on a physical Mac. No hosted service,
account, telemetry, scheduler or background daemon.

## Simple installation

1. Extract the whole **Windows Setup ZIP** or **Mac Setup ZIP**.
2. Double-click **Install-Windows.cmd** or **Install-Mac.command**.
3. Follow the dialogs. Python installs privately; no Python/Git/Homebrew setup.
4. Approve the requested Mac permissions/settings yourself, then choose **Turn ON**.

Already-installed Hermes, OpenAI Codex or Claude Code required. One ready agent is
selected automatically; multiple profiles show a choice. Each agent handles its
own sign-in. Installing Ballz alone does not change any agent profile.

Windows: reopen **Ballz2theWALL** from Start. Mac: open **Ballz2theWALL.command** in
`~/Applications`. Mac permissions are requested for **Terminal**, which launches
both setup and the selected agent. Existing unrelated background agents do not
inherit these approvals. Windows installs for the current account without UAC;
administrator-only work still needs a separately approved elevated launch.

**OFF restores saved runtime settings after you close the agent window.** It does
not kill existing processes, undo completed work or revoke macOS permissions.
This is not yet the separate desktop companion/admin-helper product.

These local-alpha bundles are not code-signed/notarized public installers.
Details: [guided setup](docs/GUIDED-SETUP.md).

## Get moving

From this repository:

```bash
uv tool install .
ballz --version
ballz doctor

# Read-only preview. Select the exact native profile/home you intend to change.
ballz plan hermes --home "$HOME/.hermes"

# Persist native permissions. Returns a rollback receipt.
ballz apply hermes --home "$HOME/.hermes"

# Start an agent with the selected home and working directory.
ballz run hermes --home "$HOME/.hermes" --cwd "$PWD" --interactive
```

`apply` is the write action. No hidden rollout to other profiles. No automatic
restart of existing gateways. A config write is not proof an already-running
agent adopted it.

Prefer an immutable wheel for deployment: `uv tool install /absolute/path/to/ballz2thewall-0.2.0a1-py3-none-any.whl`.
No PyPI publication is claimed.

## One contract, three runtimes

- **Hermes:** `--yolo`, persistent `approvals.mode: off`, unattended/cron/single-query
  approvals set to `approve`, local terminal backend and private/LAN URL access.
- **OpenAI Codex:** `--dangerously-bypass-approvals-and-sandbox`, persistent
  `approval_policy = "never"`, `sandbox_mode = "danger-full-access"`, environment
  inheritance set to `all`. `--inherit-secrets` additionally disables the default
  secret-name filter; explicit existing exclusion rules remain.
- **Anthropic Claude Code:** `--dangerously-skip-permissions`, persistent
  `permissions.defaultMode = "bypassPermissions"`, native shell sandbox disabled.

`openai` aliases `codex`; `anthropic` aliases `claude`. These adapt the actual
agent CLIs, not remote model APIs. API access alone cannot grant filesystem or
shell access to a model.

```bash
ballz plan codex --home "$HOME/.codex" --inherit-secrets
ballz apply claude --home "$HOME/.claude"
ballz run codex --home "$HOME/.codex" --cwd "$PWD" --prompt-file task.txt
ballz run claude --home "$HOME/.claude" --cwd "$PWD" --prompt-file task.txt

# Inspect a launch without resolving secrets, writing config or calling a model.
ballz run hermes --home "$HOME/.hermes" --cwd "$PWD" --prompt-file task.txt --dry-run
```

`run` does not persist config. Hermes run requires a local terminal backend; if
that home explicitly configures Docker/SSH/Modal, apply the local profile first.
Backend validation honors `terminal.backend` before legacy `terminal.env_type`.
Stored messaging `terminal.cwd` does not block CLI launch: the selected `--cwd`
is passed to the native process and `TERMINAL_CWD`. Explicit Hermes roots are
pinned with `--profile default`; named profile homes retain their native pinning.
Sticky `active_profile` markers are left untouched.
Native deny rules, instruction-file guards, configured tools, hook trust,
organization policies and provider-side rules are not rewritten. Operating-system
access is that of the launching account, not automatic root/Administrator.

## Chrome: use the session, not a vault dump

Use an authenticated browser session through the runtime's supported integration.

**Hermes:** attach an explicitly supplied existing CDP endpoint:

```bash
ballz browser-check http://127.0.0.1:9222
ballz apply hermes --home "$HOME/.hermes" --cdp http://127.0.0.1:9222
```

`browser-check` reads only `/json/version`. It does not enumerate tabs, copy
cookies, expose debugger WebSocket URLs or establish that any site is logged in.
The endpoint must already exist and be reachable from the runtime's host. WSL
and Windows are different hosts for browser integration purposes.

**Claude:** `ballz run claude --home "$HOME/.claude" --cwd "$PWD" --interactive --chrome`.
This selects Claude's native Chrome extension integration; extension installation,
pairing and host support are separate prerequisites.

**Codex:** use a separately configured browser MCP. No built-in CDP bridge here.

Chrome-saved password extraction, Login Data/Local State decryption, cookie
harvesting and OS-unlock bypass are not included. Modern Chrome also restricts
remote debugging of its default profile. Ballz does not kill your browser or
copy profiles to work around it.

## Credentials without copy/paste

Native CLIs retain their own OAuth/API authentication. Nothing is copied from
one runtime home into another. A fresh empty home is not logged in.

For selected extra credentials, resolve references into the child process environment:

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

Providers: inherited environment, authenticated official 1Password CLI (`op`),
optional Python `keyring`. No arbitrary shell-based secret providers or automatic
credential scanning. Dry runs resolve nothing. Binding references never contain
literal passwords. The controller omits secret values from its output and receipts;
the launched agent's output, tools and session logging remain that runtime's concern.

## Rollback and receipts

```bash
ballz rollback RECEIPT_ID
```

Default state: `${XDG_STATE_HOME:-~/.local/state}/ballz2thewall` on POSIX;
`%LOCALAPPDATA%/Ballz2theWALL/state` on Windows.
A custom `--state-dir /path` must be used consistently for apply and rollback.
POSIX state uses owner-only `0700` directories and `0600` backups. Native Windows
uses owner-only protected ACLs, byte-range locking, reparse/hardlink rejection and
write-through atomic replacement. ON/OFF journals use an isolated transaction
store beneath `controller/activations/`; use `ballz off`, not plain rollback, for
these managed activations.

- Atomic single-file replacements, verified hashes, advisory controller lock.
- Original config bytes and mode retained; backups/receipts use `0600`.
- Reapplying identical settings is a no-op.
- Rollback restores the exact original or removes a file Ballz created.
- Later edits cause a drift error, not a forced overwrite.
- Prepared receipts support recovery if a process stops around the config write.
- Rollback persists `rolling_back` before restoration; retry resumes after an
  interruption. Already-restored originals (including 0.1.0 receipts) are
  acknowledged without rewriting the target. Unrelated edits still fail on drift.
- YAML/JSON formatting may change during apply. TOML comments are retained.
- Backups can contain pre-existing secrets; keep the state directory local and
  out of version control. Receipts contain hashes and paths, not config contents.

This is a local operator transaction log, not an adversarially signed audit
service. Other native editors do not take Ballz's advisory lock; avoid concurrent
configuration changes. Rollback does not undo agent task actions, model calls,
account activity or browser navigation.

## Install the skill

The wheel includes the canonical skill. Print it with `ballz skill`, or install it
into an explicit skills root:

```bash
ballz skill --dest "$HOME/.hermes/skills"
# Claude Code example:
ballz skill --dest "$HOME/.claude/skills"
```

The `ballz skill --dest` command writes only `ballz2thewall/SKILL.md` and returns a rollback receipt.
For Codex or another host, select that host's documented skills root explicitly.
Loading the skill itself does not activate full access.

## Development

```bash
uv venv .venv
uv pip install --python .venv/bin/python -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests scripts
.venv/bin/python -m build
```

See [adapter contracts](docs/ADAPTERS.md), [design and acceptance criteria](docs/DESIGN.md),
and [verification](docs/VERIFICATION.md). Discovery and base-selection receipts live
in `docs/discovery/`. Source discovery executed no candidate code.

MIT licensed. Local alpha, not a claim of universal unrestricted access.
