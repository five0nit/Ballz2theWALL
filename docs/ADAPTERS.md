# Native adapter contract

`Adapter` in `src/ballz2thewall/adapters.py` defines executable identity, native
home environment variable, config filename, supported permission flag, tested
version, dotted configuration values, argv and runtime environment updates.
Registry aliases resolve to the same adapter object; no duplicate provider logic.

## Verified contract targets

- Hermes Agent 0.21.1: `HERMES_HOME/config.yaml`, `hermes chat --yolo`;
  one-shot input through `--oneshot --query-file -`.
- Codex CLI 0.152.0: `CODEX_HOME/config.toml`,
  `codex exec --dangerously-bypass-approvals-and-sandbox -`;
  native stdin prompt, environment-policy overrides through `-c`.
- Claude Code 2.1.201: `CLAUDE_CONFIG_DIR/settings.json`,
  `claude --dangerously-skip-permissions --print` with stdin prompt;
  `--settings '{"sandbox":{"enabled":false}}'` is a process-local override.

`doctor` runs `--version` and `--help`, never an auth command. `ready` means the
executable advertises the permission flag, NOT that its model login works or all
config keys remain compatible across arbitrary future versions. Version mismatch
is surfaced. Config changes on unverified versions need additional native checks.
Claude print mode may silently ignore invalid settings; CLI-help success alone
is not a schema-validation proof.

## Config boundaries

Only the named user-owned native config is edited. Other properties are retained.
Codex `default_permissions` conflicts with legacy `sandbox_mode`; persistent apply
reports the conflict rather than corrupting a newer permission-profile config.
Use a process-local launch or explicitly migrate that config separately.

`run` and `apply` differ deliberately: apply selects stored settings for future
processes; run uses native process-local flags and leaves those settings alone.
Hermes config can override TERMINAL_ENV, so a stored nonlocal backend must be
changed explicitly before a local full-access launch. Private URL allowances are
persisted by apply, not universally enforced by launch flags.

## Add an adapter

1. Verify its installed CLI help and current official docs. Record exact version,
   config precedence, parser semantics, managed-policy behavior and home variable.
2. Add a registry entry and minimal settings/argv/environment implementation.
   Split into separate classes when genuinely different lifecycles warrant it.
3. Do not confuse a model vendor with an agent runtime. A remote API without a
   local tool host cannot support this permission contract.
4. Add config-preservation, missing-runtime, unsupported-flag, exact argv/stdin,
   no-secret-output and real apply/rollback tests. Use isolated homes.
5. Verify the actual native parser, then one bounded model task if authorized and
   authenticated. Mark each gate separately; mocks are not native evidence.
6. Update the bundled skill and this support matrix. Unsupported capabilities
   must return explicit errors, not a success-shaped fallback.

## Official references

- https://hermes-agent.nousresearch.com/docs/user-guide/configuration
- https://hermes-agent.nousresearch.com/docs/user-guide/secrets/
- https://developers.openai.com/codex/security/
- https://developers.openai.com/codex/config-reference/
- https://developers.openai.com/codex/config-schema.json
- https://code.claude.com/docs/en/permissions
- https://code.claude.com/docs/en/settings
- https://developer.chrome.com/blog/remote-debugging-port
