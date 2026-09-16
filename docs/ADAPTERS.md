# Native adapters and machine bindings

This page describes **0.3.0a0.dev6 source**, not the v0.2.0a2 download feature set.
See [verification](VERIFICATION.md) for which gates were actually exercised.

## Native runtime contracts

`Adapter` in `src/ballz2thewall/adapters.py` defines executable identity, native
home environment variable, config filename, permission flag, tested version,
configuration values, argv and environment updates. Aliases share one adapter.

| Runtime contract target | Selected config | Native launch |
| --- | --- | --- |
| Hermes Agent 0.21.1 | `HERMES_HOME/config.yaml` | `hermes chat --yolo`; one-shot `--oneshot --query-file -` |
| Codex CLI 0.152.0 | `CODEX_HOME/config.toml` | `codex exec --dangerously-bypass-approvals-and-sandbox -` |
| Claude Code 2.1.201 | `CLAUDE_CONFIG_DIR/settings.json` | `claude --dangerously-skip-permissions --print`, stdin prompt; process-local `--settings '{"sandbox":{"enabled":false}}'` |
| OpenClaw 2026.6.1 | Selected default `.openclaw/openclaw.json` and `exec-approvals.json` | Embedded `agent --local`; prior native policy ON/apply required |

These are recorded contract targets, not claims that every version or authenticated
session is verified. `doctor` runs version/help checks, not login. It reports a
version mismatch without making version equality a hard gate. Claude print mode
may ignore invalid settings; CLI-help success alone is not schema validation.

Explicit Hermes root homes use `--profile default` to defeat sticky profile
selection. Named homes immediately below `profiles` keep native pinning without
that flag. No `active_profile` marker is rewritten.

## Managed machine connection

`ballz on` adds native settings and a machine activation; `apply` edits native
settings only. `run` launches but does not activate or persist configuration.
The managed server uses the installed Python with `-I -m ballz2thewall machine
serve`, an explicit state directory and activation ID. Its registration name is
`ballz2thewall_machine`; the MCP server identifies as `Ballz2theWALL-machine`.

| Runtime | Registration | Binding limits |
| --- | --- | --- |
| Hermes | `mcp_servers.ballz2thewall_machine` in selected YAML | `connect_timeout: 30`, `timeout: 120` |
| Codex | `mcp_servers.ballz2thewall_machine` in selected TOML | `startup_timeout_sec = 30`, `tool_timeout_sec = 120` |
| Claude | Inline `--mcp-config` containing `mcpServers.ballz2thewall_machine` | Only matching ON-home `ballz run` / launcher startup; no MCP write into `settings.json` or separate `~/.claude.json`; no `--strict-mcp-config` |
| OpenClaw | `mcp.servers.ballz2thewall_machine` in native JSON5 config | `connectTimeout: 30`, `timeout: 120`; schema/effective-policy validation remains required |

An existing namesake server or non-mapping MCP section is rejected rather than
overwritten. Only allowlisted desktop connection/environment metadata is stored,
not the whole environment or provider credentials. Other MCP registrations remain.
The client tool timeout is separate from `machine_exec.timeout`: use background
jobs for long commands instead of assuming `timeout:0` changes the client deadline.

A binding write proves registration, not authenticated execution. Prior native
Hermes connection, Codex parsing and OpenClaw parsing/discovery evidence are
historical. Current dev6 authenticated startup and a real tool call with verified
OFF restoration are separate owner-acceptance gates; Claude authenticated startup
must not be inferred from its inline JSON construction.

## Machine tool contract

The local tools are `machine_status`, `machine_exec`, `machine_file` and
`machine_job`. Dynamic driver tools have the `desktop_` prefix. Required packages
are `mcp==1.30.0` and `cua-driver==0.28.1`.

`machine check` checks dependencies/importability and native driver version only.
Desktop/browser tools run through `cua-driver mcp --direct --no-overlay` on the
runtime host with `CUA_DRIVER_PERMISSION_MODE=unrestricted` and
`CUA_DRIVER_DANGEROUSLY_BYPASS_APPROVALS=1`. OS grants remain separate. This owns a
driver process rather than attaching to the user's shared driver daemon. Driver
telemetry has its own controls; do not advertise the complete stack as telemetry-free.

See [capabilities](CONSUMER-ACCESS.md), [command jobs](COMMAND-JOBS.md) and
[guided setup](GUIDED-SETUP.md) for tool bounds, Windows approval and OFF behavior.

## Configuration and platform boundaries

Only selected configuration files are edited. Codex `default_permissions` can
conflict with legacy `sandbox_mode`; persistent apply reports that conflict instead
of damaging a newer permissions-profile config. Use a process-local launch or
explicitly migrate it separately.

Hermes validation follows `terminal.backend` before legacy `terminal.env_type`.
A stored Docker/SSH/Modal backend must be changed explicitly before a local launch.
Ballz pins subprocess cwd and `TERMINAL_CWD` to `--cwd`, superseding stored messaging
cwd. Private URL allowances are persisted by apply, not universally by launch flags.

OpenClaw is local-only: default `.openclaw` layout on Linux/WSL/macOS. Native
Windows, named profiles, `$include`, remote gateways, node execution, provider tool
overrides and explicit per-agent runtime overrides are rejected. Native schema and
scoped effective-policy checks run before ON is reported; failed validation triggers
rollback. The interactive wrapper forwards to `agent --local` without starting a
gateway. Native `--message` exposes prompt text in child argv; dry-run redacts it.
Read [OPENCLAW.md](OPENCLAW.md) as its policy contract, not proof of dev6 model/tool
acceptance. Mac source support is not physical Mac acceptance.

Managed policies, hook trust, provider rules and OS rights remain applicable.
OpenClaw is an explicit local-policy exception: ON clears configured `tools.deny`
globally and for existing agents as documented in [OPENCLAW.md](OPENCLAW.md);
OFF restores the saved configuration. The Windows helper is separate owner-approved elevation for the same
user, not SYSTEM/root on other platforms. WSL and native Windows do not share a
desktop-control host automatically. Firmware/bootloader control is not implemented.

## Adding an adapter

1. Inspect the installed CLI and official docs; record version, parser semantics,
   config precedence, home variables and managed-policy behavior.
2. Add settings/argv/environment and the correct native MCP envelope. Avoid editing
   unrelated global config to work around selected-home boundaries.
3. Test preservation, missing/unsupported runtime failures, exact argv/stdin,
   credential redaction, ON/OFF and apply/rollback in isolated homes.
4. Verify the native parser, then an authorized bounded authenticated tool task.
   Record config write, parser success, connection, execution and OFF separately.
5. Update this matrix and the bundled skill. Never turn unsupported behavior into
   a success-shaped fallback.

## Official references

- https://hermes-agent.nousresearch.com/docs/user-guide/configuration
- https://hermes-agent.nousresearch.com/docs/user-guide/secrets/
- https://developers.openai.com/codex/security/
- https://developers.openai.com/codex/config-reference/
- https://developers.openai.com/codex/config-schema.json
- https://code.claude.com/docs/en/permissions
- https://code.claude.com/docs/en/settings
- https://developer.chrome.com/blog/remote-debugging-port
