"""Explicit scopes: plan is read-only, apply persists, run launches, rollback restores."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from importlib.resources import files
from pathlib import Path

from . import __version__
from .adapters import ADAPTERS, ALIASES, get_adapter
from .admin import AdminError
from .config import Plan, checked_path, make_plan, parse
from .doctor import inspect_runtime, require_runtime
from .store import Store


def output(value: dict) -> None:
    print(json.dumps(value, indent=2))


def state_root() -> Path:
    if os.name == "nt":
        return Path(os.getenv("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "Ballz2theWALL/state"
    return Path(os.getenv("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "ballz2thewall"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ballz", description="Ballz2theWALL — full-access runtime profiles")
    p.add_argument("--version", action="version", version=f"Ballz2theWALL {__version__}")
    commands = p.add_subparsers(dest="command", required=True)
    names = list(ADAPTERS) + list(ALIASES)
    doc = commands.add_parser("doctor", help="Inspect native flags; no auth reads or model calls")
    doc.add_argument("adapter", nargs="?", choices=names)
    doc.add_argument("--home", type=Path)
    for name in ("plan", "apply", "run"):
        sub = commands.add_parser(name)
        sub.add_argument("adapter", choices=names)
        sub.add_argument("--home", required=True, type=Path, help="Exact native runtime home")
        sub.add_argument("--cdp", help="Hermes: explicit existing HTTP(S) Chrome debugging endpoint")
        sub.add_argument("--inherit-secrets", action="store_true", help="Codex: include secret-named inherited env vars")
        if name in {"apply", "run"}:
            sub.add_argument("--state-dir", type=Path, default=state_root())
        if name == "run":
            sub.add_argument("--cwd", required=True, type=Path)
            sub.add_argument("--model")
            sub.add_argument("--chrome", action="store_true", help="Claude in Chrome native extension")
            sub.add_argument("--secret", action="append", default=[], metavar="NAME=PROVIDER:REFERENCE")
            sub.add_argument("--dry-run", action="store_true", help="Render launch metadata, resolve no secrets")
            mode = sub.add_mutually_exclusive_group(required=True)
            mode.add_argument("--prompt", help="One-shot prompt (use --prompt-file to avoid process-list exposure)")
            mode.add_argument("--prompt-file", type=Path, help="UTF-8 prompt file; '-' reads stdin. OpenClaw forwards content through native --message")
            mode.add_argument("--interactive", action="store_true")
    back = commands.add_parser("rollback")
    back.add_argument("receipt_id")
    back.add_argument("--state-dir", type=Path, default=state_root())
    browser = commands.add_parser("browser-check", help="Read endpoint version metadata only")
    browser.add_argument("url")
    skill = commands.add_parser("skill", help="Print or install the bundled agent skill")
    skill.add_argument("--dest", type=Path, help="Explicit skills root; writes ballz2thewall/SKILL.md only")
    skill.add_argument("--state-dir", type=Path, default=state_root())
    setup = commands.add_parser("setup", help="Guided first-run OS permission and agent setup")
    setup.add_argument("--gui", action="store_true", help="Native dialogs (default on Windows/macOS)")
    setup.add_argument("--check", action="store_true", help="Inspect only; never request permissions or activate")
    setup.add_argument("--state-dir", type=Path, default=state_root())
    on = commands.add_parser("on", help="Enable one selected agent; journal its prior settings")
    on.add_argument("adapter", choices=names)
    on.add_argument("--home", required=True, type=Path)
    on.add_argument("--state-dir", type=Path, default=state_root())
    for action in ("off", "status"):
        sub = commands.add_parser(action)
        sub.add_argument("--state-dir", type=Path, default=state_root())
    machine = commands.add_parser("machine", help="Owned machine tools, desktop bridge and approved administration")
    machine.add_argument("action", choices=["check", "serve", "tool", "tools", "admin-on", "admin-off", "admin-status"])
    machine.add_argument("--state-dir", type=Path, default=state_root())
    machine.add_argument("--activation-id")
    machine.add_argument("--tool")
    machine.add_argument("--arguments", default="{}", help="JSON object for one tool call")
    machine.add_argument("--no-desktop", action="store_true", help="Serve shell/files only on headless hosts")
    return p


def machine_command(args) -> int:
    import asyncio

    from . import admin, machine
    from .onboarding import Activation
    if args.action == "check":
        from .machine_check import inspect_machine
        report = inspect_machine()
        output(report)
        return 0 if report["status"] == "ready" else 2
    if args.action == "admin-status":
        output(admin.status(args.state_dir))
        return 0
    if args.action == "admin-off":
        result = admin.disable(args.state_dir)
        output(result)
        return 2 if result.get("error") or result.get("status") != "off" else 0
    identity = args.activation_id or Activation(args.state_dir).status().get("id")
    machine.require_on(args.state_dir, identity)
    if args.action == "admin-on":
        result = admin.enable(args.state_dir)
        output(result)
        return 0 if result.get("status") == "ready" and result.get("elevated") is True else 2
    if args.action == "serve":
        asyncio.run(machine.serve(args.state_dir, identity, desktop=not args.no_desktop))
        return 0
    if args.action == "tools":
        output({"tools": [t.model_dump(mode="json") for t in machine.local_tools()],
                "desktop": asyncio.run(machine.driver_call(args.state_dir, identity, None, {}))})
        return 0
    if not args.tool:
        raise ValueError("machine tool requires --tool")
    try:
        arguments = json.loads(args.arguments)
    except (ValueError, TypeError):
        raise ValueError("--arguments must be valid JSON") from None
    if not isinstance(arguments, dict):
        raise ValueError("--arguments must be a JSON object")
    if args.tool.startswith("desktop_"):
        result = asyncio.run(machine.driver_call(args.state_dir, identity, args.tool, arguments))
    else:
        result = machine.call_local(args.state_dir, identity, args.tool, arguments)
    output(result)
    return 2 if (result.get("isError") or result.get("error") or result.get("timed_out")
                 or result.get("cancelled") or result.get("revoked") or result.get("returncode", 0) != 0) else 0


def run(args, adapter, home: Path, cdp: str | None) -> int:
    from .credentials import describe_bindings, resolve_bindings
    # Validate before probing native CLIs or resolving any credential.
    descriptors = describe_bindings(args.secret)
    reserved = {"HERMES_HOME", "CODEX_HOME", "CLAUDE_CONFIG_DIR", "HOME", "PATH",
                "TERMINAL_ENV", "TERMINAL_CWD", "HERMES_YOLO_MODE", "BROWSER_CDP_URL",
                "OPENCLAW_STATE_DIR", "OPENCLAW_CONFIG_PATH", "OPENCLAW_OAUTH_DIR", "OPENCLAW_HOME",
                "OPENCLAW_AGENT_DIR", "PI_CODING_AGENT_DIR", "OPENCLAW_PROFILE"}
    if any(binding.split("=", 1)[0] in reserved for binding in args.secret):
        raise ValueError("Credential bindings cannot replace runtime scope or executable resolution variables")
    argv = adapter.argv(interactive=args.interactive, model=args.model, chrome=args.chrome,
                        inherit_secrets=args.inherit_secrets, home=home)
    env_updates = adapter.environment(home, cdp)
    if adapter.name == "claude":
        from .machine import require_on
        from .machine_bindings import claude_config
        from .onboarding import Activation
        active = Activation(args.state_dir).status()
        if (active.get("phase") == "on" and active.get("machine_access") is True
                and active.get("adapter") == "claude" and active.get("home") == str(home)):
            require_on(args.state_dir, active["id"])
            spec = claude_config(args.state_dir, active["id"])
            # Terminate variadic --mcp-config with a known native option, not
            # a prompt/config filename. Preserve other installed MCP servers.
            argv = [argv[0], "--mcp-config", json.dumps(spec), *argv[1:]]
    cwd = args.cwd.expanduser().absolute()
    if not cwd.is_dir():
        raise ValueError("--cwd must be an existing directory")
    if not home.is_dir():
        raise ValueError("--home must exist; select an authenticated runtime home or apply first")
    target = checked_path(home / adapter.filename)
    if adapter.name == "hermes":
        env_updates["TERMINAL_CWD"] = str(cwd)
    if adapter.name == "hermes" and target.exists():
        native = parse(target.read_bytes(), adapter.filename)
        terminal = native.get("terminal", {})
        if (not isinstance(terminal, dict)
                or terminal.get("backend", terminal.get("env_type", "local")) != "local"):
            raise ValueError("Hermes home selects a nonlocal terminal; use ballz apply for the local profile first")
        # Native local CLI replaces stored terminal.cwd with os.getcwd(). The
        # subprocess cwd and pinned TERMINAL_CWD above are the effective scope.
    if args.dry_run:
        output({"status": "dry_run", "adapter": adapter.name, "argv": argv, "cwd": str(cwd),
                "environment_overrides": env_updates, "credentials": descriptors,
                "prompt": ("interactive" if args.interactive else
                           "native --message; content omitted" if adapter.name == "openclaw"
                           else "stdin; content omitted"),
                "auth": "native runtime retains its own auth store"})
        return 0
    report = require_runtime(adapter, home)
    argv[0] = report["executable"]
    if args.interactive and not sys.stdin.isatty():
        raise ValueError("Interactive mode requires a TTY; use --prompt-file for automation")
    prompt = args.prompt
    if args.prompt_file:
        prompt = sys.stdin.read() if str(args.prompt_file) == "-" else args.prompt_file.read_text(encoding="utf-8")
    if not args.interactive and not (prompt and prompt.strip()):
        raise ValueError("One-shot prompt must not be empty")
    env = dict(os.environ)
    env.update(resolve_bindings(args.secret))
    env.update(env_updates)
    if adapter.name == "openclaw":
        from .openclaw import make_plans
        from .openclaw_runtime import launch, verify_native
        if any(p.before != p.after for p in make_plans(home)):
            raise ValueError("OpenClaw policy is not ON; use ballz on or ballz apply first")
        verify_native(home, argv[0])
        return launch(argv, prompt, args.interactive, cwd, env)
    # Other adapters accept stdin. OpenClaw requires its native --message flag.
    return subprocess.run(argv, cwd=cwd, env=env, input=prompt, text=True, check=False).returncode


def report_error(args, message: str) -> None:
    output({"status": "error", "error": message})
    if args.command == "setup" and getattr(args, "gui", False) and not args.check:
        from .onboarding import Dialogs
        try:
            Dialogs().message("Setup needs attention", message + "\n\nReopen Ballz2theWALL to retry. No success is assumed.")
        except (ValueError, OSError, subprocess.SubprocessError):
            pass


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "machine":
            return machine_command(args)
        if args.command in {"setup", "on", "off", "status"}:
            from .onboarding import Activation, augment_path, check_setup, wizard
            augment_path()
            if args.command == "setup":
                if args.check:
                    output(check_setup(args.state_dir))
                    return 0
                return wizard(args.state_dir)
            control = Activation(args.state_dir)
            if args.command == "on":
                from .machine_check import require_ready
                require_ready()
                output(control.enable(args.adapter, args.home, machine_access=True))
            elif args.command == "off":
                output(control.disable())
            else:
                output(control.status())
            return 0
        if args.command == "doctor":
            selected = [get_adapter(args.adapter)] if args.adapter else list(ADAPTERS.values())
            reports = [inspect_runtime(a, args.home) for a in selected]
            output({"runtimes": reports, "machine_access": "current OS account only; no privilege escalation",
                    "provider_rules": "unchanged", "browser_auth": "not_probed"})
            return 0 if all(r["status"] == "ready" for r in reports) else 2
        if args.command == "rollback":
            from .openclaw import OpenClawStore
            bundle = checked_path(args.state_dir / f"{args.receipt_id}.bundle.json")
            store = OpenClawStore(args.state_dir) if bundle.exists() else Store(args.state_dir)
            output(store.rollback(args.receipt_id))
            return 0
        if args.command == "browser-check":
            from .browser import probe_cdp
            report = probe_cdp(args.url)
            output(report)
            return 0 if report["connected"] else 2
        if args.command == "skill":
            content = files("ballz2thewall").joinpath("skill/SKILL.md").read_bytes()
            if not args.dest:
                print(content.decode(), end="")
            else:
                target = checked_path(args.dest / "ballz2thewall" / "SKILL.md")
                before = target.read_bytes() if target.exists() else None
                output(Store(args.state_dir).apply(Plan(target, before, content, {}, "skill")))
            return 0
        adapter = get_adapter(args.adapter)
        home = args.home.expanduser().absolute()
        cdp = args.cdp
        if cdp:
            from .browser import validate_cdp_url
            cdp = validate_cdp_url(cdp)
        adapter.settings(cdp, args.inherit_secrets)
        if args.command == "run":
            return run(args, adapter, home, cdp)
        if adapter.name == "openclaw":
            from .openclaw import OpenClawStore, make_plans
            from .openclaw_runtime import apply_verified
            plans = make_plans(home)
            if args.command == "plan":
                output({"adapter": "openclaw", "files": [p.public() for p in plans]})
            else:
                report = require_runtime(adapter, home)
                output(apply_verified(OpenClawStore(args.state_dir), plans, home, report["executable"]))
            return 0
        plan = make_plan(adapter, home, cdp, args.inherit_secrets)
        if args.command == "plan":
            output(plan.public())
        else:
            require_runtime(adapter, home)
            output(Store(args.state_dir).apply(plan))
        return 0
    except (ValueError, AdminError) as exc:
        report_error(args, str(exc))
        return 2
    except (OSError, UnicodeError, subprocess.SubprocessError):
        report_error(args, "File or process operation failed; check explicit paths and access")
        return 2
    except KeyboardInterrupt:
        return 130
