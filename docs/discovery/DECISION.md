# Ballz2theWALL base decision

Target: Python 3.11+ local-first MIT CLI and installable agent skill for explicit full-access runtime configuration, initially Hermes, OpenAI Codex and Anthropic Claude Code; reversible native-config changes, doctor, shell-free launching, existing native auth and user-selected credential references.

Discovery receipt: discovery.json and discovery.md in this directory. Candidate execution: none. CLI result: complete discovery; provisional selective-reuse of agent-box-cli 1.0.0. Required upstream checks remain unresolved: published-package source identity and untrusted test execution. No claim these passed.

Manual disposition: build-clean for the small configuration controller; integrate official existing agent CLIs rather than reimplement agents or fork a governance platform. This is a bounded fit decision, not a claim no alternatives exist.

Reviewed candidates:
- agent-box-cli: CLI score 74.61, decision score 73.71. https://github.com/mmm-05610/agent-box commit 6c14ea8db8130f1e219328835840b4159fe8c9e7; MIT license read. Root pyproject reports 2.0.0a1, not discovery's PyPI 1.0.0. Hermes adapter source read: guest-home staging /runtime/home/.hermes, observation pipeline and governance kernel. Reject as base: sandbox/staging architecture opposes native-home controller and requires a plugin stack; package/source mismatch unresolved. No source copied.
- claude-code-agent 0.3.0: score 60.75; wrapping Claude SDK only, not cross-runtime native configuration. Static inspection unavailable. Reject as base within current scope; license/source execution checks unknown.
- langchain-claude-code-cli 0.1.0: score 56.25; LangChain wrapper rather than native config controller. Reject as base. Uninspected package evidence remains provisional.
- local Hermes: score 53.00; existing installation's CLI and native config source inspected at dcf725e6d2c97bcdb2b3f09cf0fb7de4f95233cc. Broad suite not executed; runtime reused as subprocess, no vendoring. CLI's license blocker arose from free-form MIT normalization, not an observed nonpermissive license.

Native interfaces verified live: Hermes v0.21.1 --yolo and approvals.mode=off, terminal.backend=local; Codex 0.152.0 --dangerously-bypass-approvals-and-sandbox; Claude Code 2.1.201 --dangerously-skip-permissions and --chrome. Native config keys require executable integration tests against temporary homes before claiming verified.

Browser scope: attach to operator-provided existing CDP session or native Chrome integration; no profile database/password/cookie extraction, OS decryption bypass or browser auto-killing. Credentials: explicit environment/manager references, inherited native authentication. No provider-side jailbreak, managed-policy tampering, privilege escalation, firewall changes, live-agent activation or publishing included.
