---
name: ballz2thewall
description: Use when enabling native full-access agent runtimes. Configure Hermes, OpenAI Codex, Anthropic Claude Code and local OpenClaw with explicit homes, credential references and reversible receipts.
license: MIT
metadata:
  version: 0.2.0a2
  platforms: [linux, macos, windows, wsl]
---

# Ballz2theWALL

**Less asking. More doing. Actual permissions, not magic prompts.**

Use for operator-requested native full-access runtime setup. This skill is an
interface to the `ballz` CLI, not an override of provider instructions or a
credential extractor. Loading the skill makes no machine changes.

## Guided setup

For nontechnical users, extract the platform Setup ZIP and double-click its
installer. It installs private Python, then launches `ballz setup --gui`.
Use the installed shortcut to reopen setup. macOS 11+ guidance requests access
for Terminal, which launches setup and the agent. Native Mac acceptance remains
pending; do not label those requests runtime-verified.

`ballz setup --check` checks status without requesting grants. `ballz on AGENT
--home PATH` owns a reversible configuration transaction; `ballz off` restores
its original settings. Close the agent first: OFF does not kill running agents
or revoke OS grants. Do not imply universal desktop or administrative access.

Installing this skill alone never runs permission setup or activates a profile.
The user completes OS approvals and the agent's own sign-in personally.

## Operate

1. Verify the controller: `ballz --version`. If absent, install from the reviewed
   local repository with `uv tool install /absolute/path/to/Ballz2theWALL`, or
   install the supplied immutable wheel. Never guess a published package exists.
2. Run `ballz doctor`. This checks CLI availability and native permission flags;
   it does not prove model login, OS elevation or browser authentication.
3. Identify the exact intended runtime home. Respect `HERMES_HOME`, `CODEX_HOME`,
   and `CLAUDE_CONFIG_DIR`; do not assume another agent/profile is the target.
4. Preview: `ballz plan hermes --home /absolute/runtime/home`.
5. Persist only on the operator's requested scope:
   `ballz apply hermes --home /absolute/runtime/home`.
   Keep the returned `receipt_id` and state directory. Future processes read the
   config; do not restart live gateways to apply it without separate approval.
6. Or launch without persisting config:
   `ballz run hermes --home /absolute/runtime/home --cwd /absolute/workspace --prompt-file task.txt`.
   This starts a real agent. `--dry-run` prints the launch contract without
   resolving credentials or calling a model. `--interactive` requires a TTY.
   Explicit Hermes roots are pinned against sticky profile selection; named
   profile homes stay pinned without rewriting `active_profile`. Native backend
   precedence includes legacy `env_type`; stored messaging cwd is superseded
   by the selected local CLI working directory.
7. Roll back: `ballz rollback RECEIPT_ID`. With a custom `--state-dir`, repeat it.
   Interrupted rollback can be retried with the same receipt; already-restored
   original bytes/absence are acknowledged without rewriting the target.
   Drift is an error, not permission to overwrite someone else's later edits.

Use `codex`/`openai` for OpenAI Codex and `claude`/`anthropic` for Claude Code.
These are runtime adapters, not SDK permission switches for remote model APIs.

## OpenClaw

Use `ballz on openclaw --home "$HOME/.openclaw"`, then `ballz run openclaw
--home "$HOME/.openclaw" --cwd "$PWD" --interactive`. ON validates native schema
and host policy; OFF restores config and approvals. Linux/WSL/macOS only;
default `.openclaw` layout, no named profiles or remote nodes/gateways. Run
requires prior ON/apply. The thin terminal prompt loop forwards each message
to native `agent --local` with one session ID; no daemon is started. Native
OpenClaw takes prompt text in `--message`, so it appears in child argv; dry-run
redacts it. Configured OpenClaw workspace rules remain native. No browser adapter.

## Browser and credentials

- Hermes: pass an explicit existing HTTP(S) Chrome debugging endpoint with
  `--cdp http://127.0.0.1:9222`. Probe metadata via
  `ballz browser-check http://127.0.0.1:9222`.
- Claude: `ballz run claude ... --chrome` enables the native Chrome extension
  integration. Extension installation/pairing and supported host OS are separate.
- Codex: configure a browser MCP with the native CLI; no pretend CDP adapter.
- Existing OAuth/login stores remain the native runtime's responsibility. No
  copying between homes. A new empty home is not automatically authenticated.
- Bind one selected credential at launch:
  `--secret API_KEY=env:MY_API_KEY`,
  `--secret API_KEY=op:op://Vault/Item/field`, or
  `--secret API_KEY=keyring:service/account`.
  1Password requires an authenticated `op` CLI; keyring needs the optional extra.
  References only; never insert literal secrets into commands or prompts.
- For Codex shell tools to inherit secret-named variables, explicitly add
  `--inherit-secrets`. Existing explicit shell exclude rules still apply.
- Chrome sessions support authenticated browsing, not extraction of saved
  passwords, cookie databases, decryption keys or bypass of OS unlock prompts.

## Verify honestly

Check the generated receipt, a fresh `ballz plan` reporting `changed: false`, and
an operator-scoped real task. Report configuration write, native parsing, model
execution and browser login as separate checks. Do not substitute a mock result
for actual native runtime success.

OS permissions, managed policies, explicit deny rules, provider rules and tool
availability remain independent limits. Hermes instruction-file protection and
scanning are not disabled. No root escalation, firewall mutation, obfuscation,
profile scraping or blanket machine-wide rollout. Native agent stdout and
session logs remain controlled by that agent; keep secrets out of its prompts.

YAML/JSON apply can reformat files; rollback restores exact original bytes.
Backups may contain existing config credentials and stay in the private local
state directory, outside repositories. Only install this skill into an explicit
skills root: `ballz skill --dest /absolute/skills/root`.
