# Design and acceptance

## Objective

Convert an explicit operator choice into native full-access runtime configuration
and a reproducible launch. Measurable output: the selected home contains the
specified fields; unrelated values survive; exact rollback works; native command
flags match installed help; the installed CLI completes a real round-trip.

The skill is the agent interface, the CLI is the implementation, adapters are
native runtime contracts, and private local receipts are the recovery record.

## Components

- `adapters.py`: runtime identity, fields, flags, environment.
- `config.py`: strict YAML/TOML/JSON mappings, field merge, public plan.
- `store.py`: atomic replacement, locking, backups, hash-bound rollback.
- `doctor.py`: executable and advertised-flag checks, no model/auth calls.
- `credentials.py`: explicit env, 1Password and optional keyring references.
- `browser.py`: explicit HTTP(S) CDP endpoint metadata probe.
- `cli.py`: operator commands and subprocess lifecycle; stdin prompts, no shell.
- `skill/SKILL.md`: bundled installable instructions, no activation side effects.

## Acceptance criteria

1. All three native config formats apply, preserve unrelated settings and restore
   original bytes/mode; new files are removed on rollback.
2. Reapply is idempotent; stale plans, drift and corrupt backups fail visibly.
3. Plans and receipts do not contain pre-existing config credentials. Credential
   errors do not repeat raw inputs or external manager stderr.
4. Dry-run resolves no secrets and starts no model process.
5. Native launch gets exact argv, stdin prompt and selected home; a metacharacter
   prompt cannot become shell code in the wrapper. Exit codes propagate.
6. The wheel contains its skill and installed entrypoints work outside the source
   directory. Test minimum-supported Python as well as the development interpreter.
7. Report unit/local-integration tests, installed CLI contracts, real native parsing,
   model execution, browser authentication and global activation separately.

## Deliberate non-goals

Provider jailbreaks, credential harvesting, privilege escalation, remote policy
removal, antivirus/firewall modification, hidden persistence, browser profile
copying, public publishing and automatic rollout to other agents. Existing native
constraints remain observable; no promise that a setting defeats every boundary.

## Constraints and failure behavior

Single-file POSIX transactions; no Windows ACL implementation yet. Native editors
can race the controller between final recheck and atomic replacement. Symlinked
config paths are rejected in favor of explicit real paths. State is trusted local
operator data, not an adversarial multi-tenant journal. A future release may add
native Windows locking, more adapters and richer effective-config diagnostics.
