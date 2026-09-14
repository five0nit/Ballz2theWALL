"""Native CLI contracts. No provider prompts, auth copying or policy-file edits."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Adapter:
    name: str
    executable: str
    home_env: str
    filename: str
    flag: str
    tested_version: str

    def settings(self, cdp: str | None = None, inherit_secrets: bool = False) -> dict[str, Any]:
        if cdp and self.name != "hermes":
            raise ValueError("--cdp is supported by Hermes; Claude uses --chrome; Codex needs a browser MCP")
        if inherit_secrets and self.name != "codex":
            raise ValueError("--inherit-secrets configures Codex shell environment filtering only")
        if self.name == "hermes":
            result = {
                "approvals.mode": "off",
                "approvals.cron_mode": "approve",
                "approvals.single_query_mode": "approve",
                "approvals.unattended_mode": "approve",
                "terminal.backend": "local",
                "security.allow_private_urls": True,
                "browser.allow_private_urls": True,
            }
            if cdp:
                result["browser.cdp_url"] = cdp
            return result
        if self.name == "codex":
            result = {"approval_policy": "never", "sandbox_mode": "danger-full-access",
                      "shell_environment_policy.inherit": "all"}
            if inherit_secrets:
                result["shell_environment_policy.ignore_default_excludes"] = True
            return result
        return {"permissions.defaultMode": "bypassPermissions", "sandbox.enabled": False}

    def argv(self, *, interactive: bool, model: str | None = None, chrome: bool = False,
             inherit_secrets: bool = False) -> list[str]:
        if chrome and self.name != "claude":
            raise ValueError("--chrome requires the Claude Code adapter")
        if inherit_secrets and self.name != "codex":
            raise ValueError("--inherit-secrets requires the Codex adapter")
        if self.name == "hermes":
            args = [self.executable, "chat", self.flag]
            if not interactive:
                args += ["--oneshot", "--query-file", "-"]
        elif self.name == "codex":
            args = [self.executable] + ([] if interactive else ["exec"])
            args += [self.flag, "-c", 'shell_environment_policy.inherit="all"']
            if inherit_secrets:
                args += ["-c", "shell_environment_policy.ignore_default_excludes=true"]
        else:
            args = [self.executable, self.flag, "--settings", '{"sandbox":{"enabled":false}}']
            if not interactive:
                args.append("--print")
            if chrome:
                args.append("--chrome")
        if model:
            args += ["--model", model]
        if self.name == "codex" and not interactive:
            args.append("-")
        return args

    def environment(self, home: Path, cdp: str | None = None) -> dict[str, str]:
        self.settings(cdp=cdp)
        result = {self.home_env: str(home)}
        if self.name == "hermes":
            result.update({"TERMINAL_ENV": "local", "HERMES_YOLO_MODE": "1"})
            if cdp:
                result["BROWSER_CDP_URL"] = cdp
        return result


ADAPTERS = {
    "hermes": Adapter("hermes", "hermes", "HERMES_HOME", "config.yaml", "--yolo", "0.21.1"),
    "codex": Adapter("codex", "codex", "CODEX_HOME", "config.toml",
                     "--dangerously-bypass-approvals-and-sandbox", "0.152.0"),
    "claude": Adapter("claude", "claude", "CLAUDE_CONFIG_DIR", "settings.json",
                      "--dangerously-skip-permissions", "2.1.201"),
}
ALIASES = {"openai": "codex", "anthropic": "claude"}


def get_adapter(name: str) -> Adapter:
    try:
        return ADAPTERS[ALIASES.get(name, name)]
    except KeyError:
        raise ValueError("Unknown adapter; choose hermes, codex/openai or claude/anthropic") from None
