# Brief2Ship code-discovery receipt

## Decision

- Overall: `selective-reuse`
- Decision status: `provisional`
- Discovery status: `complete`
- Selected candidate: `pypi:agent-box-cli@1.0.0`
- Reason: `candidate agent-box-cli selected with provisional evidence; static inspection completed`
- Query: `agent CLI permission configuration Hermes Codex Claude Code`
- Started: `2026-09-14T22:34:32.753630+00:00`
- Completed: `2026-09-14T22:34:51.258198+00:00`
- Displayed / evaluated candidates: 6 / 6
- Core query: `agent CLI permission configuration Hermes Codex Claude Code`
- Requested constraints: `none extracted`
- Incomplete evidence: `none`

## Ranked candidates

| # | Score | Decision score | Coverage | Candidate | Source | Feature | Activity | Dependencies | Security | Tests | Portability | Reuse | Adoption | Recommendation | Status |
|---:|---:|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1 | 74.61 | 73.71 | 0.94 | `agent-box-cli` | `pypi` | 11.50 | 15.00 | 9.00 | 12.00 | 9.00 | 8.00 | 9.00 | 1.11 | `selective-reuse` | `provisional` |
| 2 | 60.75 | 55.01 | 0.64 | `claude-code-agent` | `pypi` | 11.25 | 11.00 | 9.00 | 13.00 | 3.00 | 8.00 | 4.00 | 1.50 | `selective-reuse` | `provisional` |
| 3 | 56.25 | 50.51 | 0.64 | `langchain-claude-code-cli` | `pypi` | 7.75 | 8.00 | 9.00 | 13.00 | 3.00 | 8.00 | 6.00 | 1.50 | `inconclusive` | `not-selected` |
| 4 | 53.00 | 43.81 | 0.47 | `local/hermes-agent` | `local` | 6.50 | 15.00 | 5.00 | 8.00 | 4.00 | 8.00 | 5.00 | 1.50 | `reject` | `blocked` |
| 5 | 46.00 | 35.66 | 0.41 | `local/hermes_cli` | `local` | 6.50 | 15.00 | 5.00 | 3.00 | 3.00 | 8.00 | 4.00 | 1.50 | `reject` | `blocked` |
| 6 | 39.50 | 29.16 | 0.41 | `local/subcommands` | `local` | 0.00 | 15.00 | 5.00 | 3.00 | 3.00 | 8.00 | 4.00 | 1.50 | `reject` | `blocked` |

## Inspection allocation

- `claude-code-agent`: `slot 1: observed blockers last, feature fit 11.25/25, then confidence-adjusted score`; status=`blocked`
- `agent-box-cli`: `slot 2: observed blockers last, feature fit 8.50/25, then confidence-adjusted score`; status=`inspected`

## Candidate evidence

### 1. `agent-box-cli`

- URL: `https://pypi.org/project/agent-box-cli/`
- Repository: `https://github.com/mmm-05610/agent-box`
- Local path: `not local`
- Homepage/demo: `unknown`
- Version: `1.0.0`
- Canonical identity: `pypi:agent-box-cli@1.0.0`
- License: `MIT`
- Normalized license: `MIT`
- Requested constraint checks: `none`
- Requirement evidence: `[]`
- Retrieval evidence: ````{"method": "bounded-name-index-and-curated-hints", "routes": ["package-name-match"], "query": "agent CLI permission configuration Hermes Codex Claude Code", "metadata_url": "https://pypi.org/pypi/agent-box-cli/json", "hydration_budget": 9, "hydration_shortlist_count": 9, "query_terms": ["agent", "claude", "cli", "code", "codex", "configuration", "hermes", "permission"], "ignored_query_terms": [], "matched_terms": {"name": ["agent", "cli"], "summary": ["claude", "code", "codex", "hermes"], "keywords": ["agent", "claude", "code", "codex"], "description": ["agent", "claude", "cli", "code", "codex", "configuration", "hermes", "permission"]}, "rank_basis": {"exact_name": 0, "term_coverage": 8, "weighted_matches": 24, "weights": {"name": 3, "summary_or_keywords": 2, "description": 1}}, "description_characters_considered": 11253, "supporting_excerpts": {"summary": ["Isolated config launcher for coding agents (Claude Code / Codex / Hermes / OpenCode)"], "keywords": ["claude-code, codex, agent, sandbox, bwrap, wsl"], "description": ["<p align=\"center\">\n  <img src=\"assets/logo.png\" alt=\"agent-box\" width=\"128\" height=\"128\">\n</p>\n\n# agent-box\n\n> **Management layer for organizing and running AI agent combinations.**\n> Keep mode", "mmunity discusses AI coding agents, the conversation often centers on\none dimension: the **model** (Claude, GPT-4, DeepSeek) or the **agent framework**\n(Claude Code, Codex, OpenCode).\n\nIn practice, an agent's behavior emerges from three lay", " manage profiles, edit configs, launch agents, check\nhealth — no terminal needed.\n\n### Linux / WSL (CLI)\n\n```bash\n# 1. System dependency\nsudo apt install bubblewrap\n\n# 2. Install agent-box\npip install agent-box-cli\n\n# 3. Install your agents"]}}````
- Activity: `2026-09-07T15:42:47Z`
- Dependencies: `3`
- Stars / forks / watchers: `2 / 1 / 0`
- Contributors / open issues: `6 / 0 (issue-only)`
- Vulnerabilities: `none observed`
- Recommendation: `selective-reuse`
- Recommendation status: `provisional`
- Hard blockers: `none`
- Required checks: `verify package-specific source, tests and license; static inspection covers the repository, not a proven package subtree; authorized sandbox test pass unavailable`
- Inspection: `inspected`
- Clone: `/tmp/brief2ship-preflight-ballz-3DRQiW/worktrees/agent-box-cli-cbc78e7757f5`
- Commit: `6c14ea8db8130f1e219328835840b4159fe8c9e7`
- Manifests: `pyproject.toml, plugins/agent-box-acp/pyproject.toml, plugins/agent-box-artifacts/pyproject.toml, plugins/agent-box-git/pyproject.toml, plugins/agent-box-harnesses/pyproject.toml, plugins/agent-box-runtime-local/pyproject.toml, plugins/agent-box-sandbox-bwrap/pyproject.toml, plugins/agent-box-session/pyproject.toml, plugins/agent-box-skills/pyproject.toml, plugins/agent-box-studio/pyproject.toml, plugins/agent-box-terminal-session/pyproject.toml, plugins/agent-box-web/pyproject.toml, plugins/agent-box-workspace-local/pyproject.toml, plugins/agent-box-web/frontend/package.json`
- Test files: `119`
- CI files: `2`

Score evidence:

- `feature_match`: `core relevance query=agent CLI permission configuration Hermes Codex Claude Code; name token coverage=0.25; description token coverage=0.50; topic token coverage=0.50; exact phrase bonus=0; candidate identity bonus=0; evidence coverage=1.00`
- `maintenance_activity`: `last activity 7 days ago; evidence coverage=1.00`
- `dependency_weight`: `declared dependencies=3; evidence coverage=1.00`
- `security_posture`: `OSV findings=0; permissive license=MIT; security policy absent; evidence coverage=1.00`
- `test_quality`: `test files/signals present; CI workflow present; test command detected; evidence coverage=1.00`
- `portability`: `cross-platform status not disproven; neutral baseline; portable ecosystem=Python; evidence coverage=0.40`
- `reuse_readiness`: `repository link present; description present; normalized permissive license=MIT; documentation present; package/build manifest present; bounded source footprint; evidence coverage=1.00`
- `adoption_health`: `strongest adoption signal=2; forks=1; watchers=0; contributors=6; open issues=0; evidence coverage=1.00`
- `decision_score`: `raw total=74.61; unknown evidence cost=0.90; decision score=max(0, raw total - unknown evidence cost)=73.71`

### 2. `claude-code-agent`

- URL: `https://pypi.org/project/claude-code-agent/`
- Repository: `https://github.com/sii-nyc/claude-code-agent`
- Local path: `not local`
- Homepage/demo: `unknown`
- Version: `0.3.0`
- Canonical identity: `pypi:claude-code-agent@0.3.0`
- License: `MIT`
- Normalized license: `MIT`
- Requested constraint checks: `none`
- Requirement evidence: `[]`
- Retrieval evidence: ````{"method": "bounded-name-index-and-curated-hints", "routes": ["package-name-match"], "query": "agent CLI permission configuration Hermes Codex Claude Code", "metadata_url": "https://pypi.org/pypi/claude-code-agent/json", "hydration_budget": 9, "hydration_shortlist_count": 9, "query_terms": ["agent", "claude", "cli", "code", "codex", "configuration", "hermes", "permission"], "ignored_query_terms": [], "matched_terms": {"name": ["agent", "claude", "code"], "summary": ["agent", "claude"], "keywords": ["agent", "claude", "code"], "description": ["agent", "claude", "cli", "code", "permission"]}, "rank_basis": {"exact_name": 0, "term_coverage": 5, "weighted_matches": 20, "weights": {"name": 3, "summary_or_keywords": 2, "description": 1}}, "description_characters_considered": 5660, "supporting_excerpts": {"summary": ["Configurable agent framework wrapping claude-agent-sdk"], "keywords": ["agent, claude, claude-code, llm, mcp"], "description": ["# claude-code-agent\n\n基于 `claude-agent-sdk` 的通用 Python 包，封装 Claude Code 的 agent 能力，提供可配置的 agent 框架。可在任意 Python 项目中安装使用。\n\n## 特性\n\n- **可配置的 Agent**：通过 `AgentC", "# claude-code-agent\n\n基于 `claude-agent-sdk` 的通用 Python 包，封装 Claude Code 的 agent 能力，提供可配置的 agent 框架。可在任意 Python 项目中安装使用。\n\n## 特性\n\n- **可配置的 Agent*", "Registry 模式（自动发现）和调用方直接传入两种方式注册 MCP 工具\n- **并行执行**：`run_agents_parallel` 支持多 agent 并发运行，可控制最大并发数\n- **CLI**：提供 `claude-code-agent run` 命令行入口，支持 YAML 配置 + 参数覆盖\n- **配置校验**：启动前自动验证配置合法性，提前暴露错误\n\n## 安装\n\n```bash\n# 基本安装\nuv add claude-code-agent\n\n# 安"]}}````
- Activity: `2026-04-16T12:23:10.289168Z`
- Dependencies: `1`
- Stars / forks / watchers: `unknown / unknown / unknown`
- Contributors / open issues: `unknown / unknown`
- Vulnerabilities: `none observed`
- Recommendation: `selective-reuse`
- Recommendation status: `provisional`
- Hard blockers: `none`
- Required checks: `verify package-specific source, tests and license; static inspection covers the repository, not a proven package subtree; static repository inspection not completed; authorized sandbox test pass unavailable`
- Inspection: `blocked`
- Clone: `not cloned`
- Commit: `unknown`
- Manifests: `none`
- Test files: `0`
- CI files: `0`

Score evidence:

- `feature_match`: `core relevance query=agent CLI permission configuration Hermes Codex Claude Code; name token coverage=0.38; description token coverage=0.25; topic token coverage=0.38; exact phrase bonus=0; candidate identity bonus=4; evidence coverage=0.65`
- `maintenance_activity`: `last activity 151 days ago; evidence coverage=1.00`
- `dependency_weight`: `declared dependencies=1; evidence coverage=1.00`
- `security_posture`: `OSV findings=0; permissive license=MIT; security policy unknown; evidence coverage=0.85`
- `test_quality`: `test evidence unknown; partial neutral score; evidence coverage=0.00`
- `portability`: `cross-platform status not disproven; neutral baseline; portable ecosystem=Python; evidence coverage=0.40`
- `reuse_readiness`: `repository link present; description present; normalized permissive license=MIT; evidence coverage=0.60`
- `adoption_health`: `adoption data unknown; partial neutral score; evidence coverage=0.00`
- `decision_score`: `raw total=60.75; unknown evidence cost=5.74; decision score=max(0, raw total - unknown evidence cost)=55.01`

### 3. `langchain-claude-code-cli`

- URL: `https://pypi.org/project/langchain-claude-code-cli/`
- Repository: `https://github.com/ChamaruAmasara/langchain-claude-code`
- Local path: `not local`
- Homepage/demo: `unknown`
- Version: `0.1.0`
- Canonical identity: `pypi:langchain-claude-code-cli@0.1.0`
- License: `MIT`
- Normalized license: `MIT`
- Requested constraint checks: `none`
- Requirement evidence: `[]`
- Retrieval evidence: ````{"method": "bounded-name-index-and-curated-hints", "routes": ["package-name-match"], "query": "agent CLI permission configuration Hermes Codex Claude Code", "metadata_url": "https://pypi.org/pypi/langchain-claude-code-cli/json", "hydration_budget": 9, "hydration_shortlist_count": 9, "query_terms": ["agent", "claude", "cli", "code", "codex", "configuration", "hermes", "permission"], "ignored_query_terms": [], "matched_terms": {"name": ["claude", "cli", "code"], "summary": ["claude", "cli", "code"], "keywords": ["claude", "code"], "description": ["agent", "claude", "cli", "code", "permission"]}, "rank_basis": {"exact_name": 0, "term_coverage": 5, "weighted_matches": 20, "weights": {"name": 3, "summary_or_keywords": 2, "description": 1}}, "description_characters_considered": 16384, "supporting_excerpts": {"summary": ["LangChain ChatModel using Claude Code CLI - use your Claude Pro/Max subscription, no API key needed"], "keywords": ["anthropic, claude, claude-code, langchain"], "description": ["k Claude Code's built-in tools:\n\n```python\nfrom langchain_claude_code import ChatClaudeCode\n\n# Full agent with filesystem + bash access\nagent = ChatClaudeCode(\n    model=\"claude-sonnet-4-20250514\",\n    max_turns=10,\n    permission_mode=\"byp", "# langchain-claude-code\n\n**Drop-in replacement for `ChatAnthropic`** that uses your Claude Pro/Max subscription — no API key needed.\n\nUses the Claude Co", "tAnthropic`** that uses your Claude Pro/Max subscription — no API key needed.\n\nUses the Claude Code CLI under the hood, so if you can run `claude`, you can use this.\n\n```bash\npip install langchain-claude-code-cli\n```\n\n## Quick Start\n\n```pyt"]}}````
- Activity: `2026-02-10T03:36:37.342167Z`
- Dependencies: `2`
- Stars / forks / watchers: `unknown / unknown / unknown`
- Contributors / open issues: `unknown / unknown`
- Vulnerabilities: `none observed`
- Recommendation: `inconclusive`
- Recommendation status: `not-selected`
- Hard blockers: `none`
- Required checks: `static repository inspection not completed; authorized sandbox test pass unavailable`

Score evidence:

- `feature_match`: `core relevance query=agent CLI permission configuration Hermes Codex Claude Code; name token coverage=0.38; description token coverage=0.38; topic token coverage=0.25; exact phrase bonus=0; candidate identity bonus=0; evidence coverage=0.65`
- `maintenance_activity`: `last activity 216 days ago; evidence coverage=1.00`
- `dependency_weight`: `declared dependencies=2; evidence coverage=1.00`
- `security_posture`: `OSV findings=0; permissive license=MIT; security policy unknown; evidence coverage=0.85`
- `test_quality`: `test evidence unknown; partial neutral score; evidence coverage=0.00`
- `portability`: `cross-platform status not disproven; neutral baseline; portable ecosystem=Python; evidence coverage=0.40`
- `reuse_readiness`: `repository link present; description present; normalized permissive license=MIT; registry reuse signals=2; evidence coverage=0.60`
- `adoption_health`: `adoption data unknown; partial neutral score; evidence coverage=0.00`
- `decision_score`: `raw total=56.25; unknown evidence cost=5.74; decision score=max(0, raw total - unknown evidence cost)=50.51`

### 4. `local/hermes-agent`

- URL: `file:///home/fiv30nit/.hermes/hermes-agent`
- Repository: `https://github.com/NousResearch/hermes-agent`
- Local path: `/home/fiv30nit/.hermes/hermes-agent`
- Homepage/demo: `unknown`
- Version: `unknown`
- Canonical identity: `repo:https://github.com/nousresearch/hermes-agent@observed-unpinned`
- License: ` MIT License  Copyright (c) 2025 Nous Research  Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:  The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.  `
- Normalized license: `unknown`
- Requested constraint checks: `none`
- Requirement evidence: `[]`
- Retrieval evidence: `{}`
- Activity: `2026-09-09T21:02:35.795241+00:00`
- Dependencies: `unknown`
- Stars / forks / watchers: `unknown / unknown / unknown`
- Contributors / open issues: `unknown / unknown`
- Vulnerabilities: `unknown`
- Recommendation: `reject`
- Recommendation status: `blocked`
- Hard blockers: `license is outside the default permissive allowlist`
- Required checks: `complete MIT body recognized; review free-form copyright and surrounding text before reuse; static repository inspection not completed; exact package-version OSV evidence unavailable; authorized sandbox test pass unavailable`

Score evidence:

- `feature_match`: `core relevance query=agent CLI permission configuration Hermes Codex Claude Code; name token coverage=0.25; description token coverage=0.00; topic token coverage=0.00; exact phrase bonus=0; candidate identity bonus=4; evidence coverage=0.65`
- `maintenance_activity`: `last activity 5 days ago; evidence coverage=1.00`
- `dependency_weight`: `dependency count unknown; neutral score; evidence coverage=0.00`
- `security_posture`: `OSV status unknown; partial neutral score; license requires review=MIT License  Copyright (c) 2025 Nous Research  Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:  The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE. ; security policy present; evidence coverage=0.15`
- `test_quality`: `test files/signals present; evidence coverage=0.35`
- `portability`: `cross-platform status not disproven; neutral baseline; portable ecosystem=Python; evidence coverage=0.70`
- `reuse_readiness`: `repository link present; description present; registry reuse signals=2; evidence coverage=0.30`
- `adoption_health`: `adoption data unknown; partial neutral score; evidence coverage=0.00`
- `decision_score`: `raw total=53.00; unknown evidence cost=9.19; decision score=max(0, raw total - unknown evidence cost)=43.81`

### 5. `local/hermes_cli`

- URL: `file:///home/fiv30nit/.hermes/hermes-agent/hermes_cli`
- Repository: `unknown`
- Local path: `/home/fiv30nit/.hermes/hermes-agent/hermes_cli`
- Homepage/demo: `unknown`
- Version: `unknown`
- Canonical identity: `repo:file:///home/fiv30nit/.hermes/hermes-agent/hermes_cli@observed-unpinned`
- License: `unknown`
- Normalized license: `unknown`
- Requested constraint checks: `none`
- Requirement evidence: `[]`
- Retrieval evidence: `{}`
- Activity: `2026-09-09T21:02:35.291575+00:00`
- Dependencies: `unknown`
- Stars / forks / watchers: `unknown / unknown / unknown`
- Contributors / open issues: `unknown / unknown`
- Vulnerabilities: `unknown`
- Recommendation: `reject`
- Recommendation status: `blocked`
- Hard blockers: `license missing or ambiguous`
- Required checks: `static repository inspection not completed; exact package-version OSV evidence unavailable; authorized sandbox test pass unavailable`

Score evidence:

- `feature_match`: `core relevance query=agent CLI permission configuration Hermes Codex Claude Code; name token coverage=0.25; description token coverage=0.00; topic token coverage=0.00; exact phrase bonus=0; candidate identity bonus=4; evidence coverage=0.65`
- `maintenance_activity`: `last activity 5 days ago; evidence coverage=1.00`
- `dependency_weight`: `dependency count unknown; neutral score; evidence coverage=0.00`
- `security_posture`: `OSV status unknown; partial neutral score; license missing; security policy absent; evidence coverage=0.15`
- `test_quality`: `test evidence unknown; partial neutral score; evidence coverage=0.00`
- `portability`: `cross-platform status not disproven; neutral baseline; portable ecosystem=Python; evidence coverage=0.70`
- `reuse_readiness`: `repository link missing; description present; registry reuse signals=2; evidence coverage=0.00`
- `adoption_health`: `adoption data unknown; partial neutral score; evidence coverage=0.00`
- `decision_score`: `raw total=46.00; unknown evidence cost=10.34; decision score=max(0, raw total - unknown evidence cost)=35.66`

### 6. `local/subcommands`

- URL: `file:///home/fiv30nit/.hermes/hermes-agent/hermes_cli/subcommands`
- Repository: `unknown`
- Local path: `/home/fiv30nit/.hermes/hermes-agent/hermes_cli/subcommands`
- Homepage/demo: `unknown`
- Version: `unknown`
- Canonical identity: `repo:file:///home/fiv30nit/.hermes/hermes-agent/hermes_cli/subcommands@observed-unpinned`
- License: `unknown`
- Normalized license: `unknown`
- Requested constraint checks: `none`
- Requirement evidence: `[]`
- Retrieval evidence: `{}`
- Activity: `2026-09-09T21:02:35.495440+00:00`
- Dependencies: `unknown`
- Stars / forks / watchers: `unknown / unknown / unknown`
- Contributors / open issues: `unknown / unknown`
- Vulnerabilities: `unknown`
- Recommendation: `reject`
- Recommendation status: `blocked`
- Hard blockers: `license missing or ambiguous`
- Required checks: `static repository inspection not completed; exact package-version OSV evidence unavailable; authorized sandbox test pass unavailable`

Score evidence:

- `feature_match`: `core relevance query=agent CLI permission configuration Hermes Codex Claude Code; name token coverage=0.00; description token coverage=0.00; topic token coverage=0.00; exact phrase bonus=0; candidate identity bonus=0; evidence coverage=0.65`
- `maintenance_activity`: `last activity 5 days ago; evidence coverage=1.00`
- `dependency_weight`: `dependency count unknown; neutral score; evidence coverage=0.00`
- `security_posture`: `OSV status unknown; partial neutral score; license missing; security policy absent; evidence coverage=0.15`
- `test_quality`: `test evidence unknown; partial neutral score; evidence coverage=0.00`
- `portability`: `cross-platform status not disproven; neutral baseline; portable ecosystem=Python; evidence coverage=0.70`
- `reuse_readiness`: `repository link missing; description present; registry reuse signals=2; evidence coverage=0.00`
- `adoption_health`: `adoption data unknown; partial neutral score; evidence coverage=0.00`
- `decision_score`: `raw total=39.50; unknown evidence cost=10.34; decision score=max(0, raw total - unknown evidence cost)=29.16`

## Source receipts

- `local`: status=`ok`, returned=`3`, rate-limit-remaining=`None`
  - Queries: `agent CLI permission configuration Hermes Codex Claude Code`
- `github`: status=`ok`, returned=`0`, rate-limit-remaining=`9`
  - Queries: `agent CLI permission configuration Hermes Codex Claude Code; agent CLI permission configuration Hermes Codex Claude`
  - Warning: `unauthenticated GitHub rate limit is low; set GH_TOKEN or GITHUB_TOKEN`
- `pypi`: status=`ok`, returned=`3`, rate-limit-remaining=`None`
  - Queries: `agent CLI permission configuration Hermes Codex Claude Code`
  - Warning: `PyPI retrieval uses observed package-name matches plus at most 6 curated hints; hydrating 9 name(s), capped at 9 JSON requests. Ranks use observed names, summaries, keywords and the first 16384 description characters; this is not full-text index search or exhaustive coverage. Limits of at least two preserve one metadata-relevant non-name hint when available, without displacing exact package names.`

## Limitations

- `JavaScript client challenges are not bypassed; PyPI uses its official Simple index`
- `local workspace discovery is read-only and bounded; receipts may contain local paths`
- `registry popularity is supporting evidence, not proof of implementation quality`
- `repository tests never execute unless both test_top and allow_untrusted_tests are set`
- `scores compare observed public metadata; missing evidence remains explicit`
