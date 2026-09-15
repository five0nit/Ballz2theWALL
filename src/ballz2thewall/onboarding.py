"""Native first-run guidance for the existing terminal controller.

macOS grants belong to Terminal, the stable responsible app used by the
.command launchers. Never claim grants for an unrelated background agent.
"""
from __future__ import annotations

import ctypes
import json
import os
import platform
import re
import subprocess
import sys
import uuid
from importlib.resources import files
from pathlib import Path

from .adapters import ADAPTERS, get_adapter
from .config import checked_path, make_plan, parse
from .doctor import inspect_runtime, require_runtime
from .store import Store, atomic_write, digest

LABELS = {"hermes": "Hermes", "codex": "OpenAI Codex", "claude": "Claude Code", "openclaw": "OpenClaw"}
SETTINGS = {
    "accessibility": "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
    "screen_recording": "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
    "full_disk_access": "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles",
    "automation": "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation",
}


class Activation:
    """One owned config transaction; journal first, exact restoration on OFF.

Each activation gets a private receipt directory before applying, so a crash
between Store.apply and the final metadata write leaves an unambiguous receipt.
OFF restores future-launch configuration, not already-running processes or TCC.
"""

    def __init__(self, state: Path):
        self.root = state.expanduser().absolute() / "controller"
        self.path = self.root / "activation.json"

    def status(self) -> dict:
        checked_path(self.path)
        if not self.path.exists():
            return {"schema": 1, "phase": "off"}
        try:
            record = dict(parse(self.path.read_bytes(), "activation.json"))
        except (ValueError, OSError, TypeError):
            raise ValueError("Invalid activation record") from None
        if (record.get("schema") != 1 or type(record.get("schema")) is not int
                or not isinstance(record.get("phase"), str)
                or record["phase"] not in {"off", "enabling", "on", "stopping"}
                or not isinstance(record.get("id"), str)
                or not re.fullmatch(r"[0-9a-f]{32}", record["id"])
                or not isinstance(record.get("adapter"), str) or record["adapter"] not in ADAPTERS
                or not isinstance(record.get("home"), str)
                or "\x00" in record["home"] or not Path(record["home"]).is_absolute()):
            raise ValueError("Invalid activation record")
        if (not isinstance(record.get("after_sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", record["after_sha256"])
                or ("receipt_id" in record and (not isinstance(record["receipt_id"], str)
                    or not re.fullmatch(r"[0-9a-f]{32}", record["receipt_id"])))
                or (record["phase"] == "on" and "receipt_id" not in record)):
            raise ValueError("Invalid activation record")
        return record

    def _save(self, record: dict) -> None:
        atomic_write(self.path, (json.dumps(record, indent=2) + "\n").encode())

    def enable(self, name: str, home: Path) -> dict:
        adapter = get_adapter(name)
        home = home.expanduser().absolute()
        if not home.is_dir():
            raise ValueError("Agent home is missing. Finish the agent's own setup first.")
        report = require_runtime(adapter, home)
        if adapter.name == "openclaw":
            return self._enable_openclaw(home, report["executable"])
        with Store(self.root).lock():
            old = self.status()
            plan = make_plan(adapter, home)
            if old["phase"] != "off":
                if old["phase"] == "on" and old["adapter"] == adapter.name and old["home"] == str(home):
                    if digest(plan.before) != old.get("after_sha256") or plan.before != plan.after:
                        raise ValueError("Agent config drift detected. Turn OFF and resolve newer edits first.")
                    return old
                raise ValueError("Turn OFF the existing activation before choosing another agent.")
            if plan.before == plan.after:
                raise ValueError("This agent already uses these full-access settings outside Ballz. "
                                 "No normal-settings baseline exists for OFF to restore.")
            record = {"schema": 1, "id": uuid.uuid4().hex, "phase": "enabling",
                      "adapter": adapter.name, "home": str(home), "after_sha256": digest(plan.after)}
            self._save(record)
            result = Store(self.root / "activations" / record["id"]).apply(plan)
            record.update(phase="on", receipt_id=result["receipt_id"])
            self._save(record)
            return record

    def _enable_openclaw(self, home: Path, executable: str) -> dict:
        from .openclaw import OpenClawStore, make_plans
        from .openclaw_runtime import apply_verified, verify_native
        with Store(self.root).lock():
            old = self.status()
            plans = make_plans(home)
            if old["phase"] != "off":
                if old["phase"] == "on" and old["adapter"] == "openclaw" and old["home"] == str(home):
                    store = OpenClawStore(self.root / "activations" / old["id"])
                    store.validate(old["receipt_id"], home)
                    if any(p.before != p.after for p in plans):
                        raise ValueError("OpenClaw config drift detected; turn OFF before retrying")
                    verify_native(home, executable)
                    return old
                raise ValueError("Turn OFF the existing activation before choosing another agent.")
            if all(p.before == p.after for p in plans):
                raise ValueError("OpenClaw already uses these settings; no baseline exists for OFF to restore")
            record = {"schema": 1, "id": uuid.uuid4().hex, "phase": "enabling",
                      "adapter": "openclaw", "home": str(home), "after_sha256": digest(plans[0].after)}
            self._save(record)
            store = OpenClawStore(self.root / "activations" / record["id"])
            result = apply_verified(store, plans, home, executable)
            record.update(phase="on", receipt_id=result["receipt_id"])
            self._save(record)
            return record

    def _disable_openclaw(self, record: dict, tx: Path) -> dict:
        from .openclaw import OpenClawStore
        store = OpenClawStore(tx)
        receipts = list(tx.glob("*.bundle.json"))
        if len(receipts) > 1 or (record.get("receipt_id") and not receipts):
            raise ValueError("OpenClaw activation bundle missing or ambiguous")
        for receipt in receipts:
            receipt_id = receipt.name.removesuffix(".bundle.json")
            metadata = store._load(receipt_id)
            if (metadata["home"] != str(Path(record["home"]).resolve())
                    or metadata["files"][0]["after_sha256"] != record["after_sha256"]
                    or (record.get("receipt_id") and record["receipt_id"] != receipt_id)):
                raise ValueError("Invalid OpenClaw activation receipt scope")
            store.rollback(receipt_id)
        record["phase"] = "off"
        self._save(record)
        return record

    def disable(self) -> dict:
        with Store(self.root).lock():
            record = self.status()
            if record["phase"] == "off":
                return record
            record["phase"] = "stopping"
            self._save(record)
            tx = self.root / "activations" / record["id"]
            if record["adapter"] == "openclaw":
                return self._disable_openclaw(record, tx)
            receipts = list(tx.glob("*.json"))
            if len(receipts) > 1:
                raise ValueError("Invalid activation: multiple transaction receipts")
            if record.get("receipt_id") and not receipts:
                raise ValueError("Activation receipt missing; previous settings cannot be restored.")
            for receipt in receipts:
                metadata = parse(receipt.read_bytes(), "receipt.json")
                expected = Path(record["home"]) / get_adapter(record["adapter"]).filename
                if (metadata.get("target") != str(expected) or metadata.get("adapter") != record["adapter"]
                        or metadata.get("after_sha256") != record.get("after_sha256")):
                    raise ValueError("Invalid activation receipt scope")
                Store(tx).rollback(receipt.stem)
            record["phase"] = "off"
            self._save(record)
            return record


def discover_agents() -> list[dict]:
    """Discover config paths only; never load auth files or select every profile."""
    results = []
    for name, adapter in ADAPTERS.items():
        default = Path.home() / {"hermes": ".hermes", "codex": ".codex", "claude": ".claude", "openclaw": ".openclaw"}[name]
        configured = os.environ.get(adapter.home_env)
        root = Path(configured).expanduser().absolute() if configured else default
        homes = [root]
        if name == "hermes" and root.parent.name != "profiles":
            profiles = root / "profiles"
            if profiles.is_dir() and not profiles.is_symlink():
                homes += sorted(p for p in profiles.iterdir() if p.is_dir() and not p.is_symlink())
        for home in homes:
            if not home.is_dir() or home.is_symlink():
                continue
            report = inspect_runtime(adapter, home)
            if report["status"] != "ready":
                continue
            label = LABELS[name] + (f" — {home.name}" if home.parent.name == "profiles" or name == "openclaw" else " — default")
            results.append({"adapter": name, "home": str(home), "label": label, **report})
    return results


def terminal_responsible() -> bool:
    """Require the supported .command/Terminal ancestry before requesting TCC."""
    pid = os.getppid()
    for _ in range(20):
        if pid <= 1:
            return False
        try:
            line = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "ppid=,comm="],
                                  capture_output=True, text=True, timeout=5, check=True).stdout.strip()
            parent, command = line.split(None, 1)
            if "/Terminal.app/Contents/MacOS/Terminal" in command:
                return True
            pid = int(parent)
        except (ValueError, OSError, subprocess.SubprocessError):
            return False
    return False


def mac_supported() -> bool:
    # Apple DTS warns these CoreGraphics calls can crash on Catalina.
    try:
        return int(platform.mac_ver()[0].split(".")[0]) >= 11
    except (ValueError, IndexError):
        return False


def mac_permissions() -> dict:
    if not mac_supported():
        return {"platform": "Darwin", "responsible_app": "unsupported_os",
                "accessibility": None, "screen_recording": None,
                "full_disk_access": "unknown", "error": "macOS 11 or newer required"}
    framework = "/System/Library/Frameworks/"
    try:
        ax = ctypes.CDLL(framework + "ApplicationServices.framework/ApplicationServices")
        cg = ctypes.CDLL(framework + "CoreGraphics.framework/CoreGraphics")
        ax.AXIsProcessTrusted.restype = ctypes.c_bool
        cg.CGPreflightScreenCaptureAccess.restype = ctypes.c_bool
        accessibility = bool(ax.AXIsProcessTrusted())
        screen = bool(cg.CGPreflightScreenCaptureAccess())
    except (OSError, AttributeError):
        accessibility, screen = None, None
    # Open-only access probe; no bytes read and no TCC database queries/writes.
    # This is evidence for one protected path, not a public universal FDA API.
    protected = Path.home() / "Library/Application Support/com.apple.TCC/TCC.db"
    try:
        fd = os.open(protected, os.O_RDONLY)
        os.close(fd)
        disk = "protected_path_accessible"
    except FileNotFoundError:
        disk = "unknown"
    except PermissionError:
        disk = "permission_needed"
    except OSError:
        disk = "unknown"
    return {"platform": "Darwin", "responsible_app": "Terminal" if terminal_responsible() else "unsupported_launcher",
            "accessibility": accessibility, "screen_recording": screen,
            "full_disk_access": disk, "automation": "per_application_on_first_use",
            "full_disk_access_check": "open-only protected-path probe; not universal FDA attestation"}


def permission_snapshot() -> dict:
    system = platform.system()
    if system == "Darwin":
        return mac_permissions()
    if system == "Windows":
        try:
            session = ctypes.c_ulong()
            ok = ctypes.windll.kernel32.ProcessIdToSessionId(os.getpid(), ctypes.byref(session))
            admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
            return {"platform": system, "session_id": session.value if ok else None,
                    "interactive_session": bool(ok and session.value != 0), "administrator": admin,
                    "desktop_permissions": "user_session; no blanket macOS-style permission popup",
                    "elevation": "UAC for separately requested administrative launches"}
        except (OSError, AttributeError):
            return {"platform": system, "interactive_session": None, "administrator": None}
    return {"platform": system, "desktop_permissions": "not_managed", "terminal": "current_account"}


def request_mac(permission: str) -> None:
    if platform.system() != "Darwin" or not terminal_responsible():
        raise ValueError("Open the Ballz2theWALL.command launcher in Terminal to approve Mac access.")
    if not mac_supported():
        raise ValueError("Mac permission setup requires macOS 11 or newer.")
    framework = "/System/Library/Frameworks/"
    if permission == "accessibility":
        cf = ctypes.CDLL(framework + "CoreFoundation.framework/CoreFoundation")
        ax = ctypes.CDLL(framework + "ApplicationServices.framework/ApplicationServices")
        key = ctypes.c_void_p.in_dll(ax, "kAXTrustedCheckOptionPrompt")
        value = ctypes.c_void_p.in_dll(cf, "kCFBooleanTrue")
        cf.CFDictionaryCreate.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
                                         ctypes.POINTER(ctypes.c_void_p), ctypes.c_long,
                                         ctypes.c_void_p, ctypes.c_void_p]
        cf.CFDictionaryCreate.restype = ctypes.c_void_p
        options = cf.CFDictionaryCreate(None, (ctypes.c_void_p * 1)(key.value),
                                        (ctypes.c_void_p * 1)(value.value), 1, None, None)
        ax.AXIsProcessTrustedWithOptions.argtypes = [ctypes.c_void_p]
        ax.AXIsProcessTrustedWithOptions.restype = ctypes.c_bool
        cf.CFRelease.argtypes = [ctypes.c_void_p]
        if not options:
            raise ValueError("Mac permission request could not be created")
        try:
            ax.AXIsProcessTrustedWithOptions(options)
        finally:
            cf.CFRelease(options)
    elif permission == "screen_recording":
        cg = ctypes.CDLL(framework + "CoreGraphics.framework/CoreGraphics")
        cg.CGRequestScreenCaptureAccess.restype = ctypes.c_bool
        cg.CGRequestScreenCaptureAccess()
    elif permission == "automation":
        result = subprocess.run(["/usr/bin/osascript", "-e", 'tell application "Finder" to get version'],
                                capture_output=True, text=True, timeout=180, check=False)
        if result.returncode:
            raise ValueError("Finder Automation was not approved. Enable Terminal → Finder in Automation.")
    elif permission != "full_disk_access":
        raise ValueError("Unknown Mac permission")


def open_settings(permission: str) -> None:
    if platform.system() != "Darwin" or permission not in SETTINGS:
        raise ValueError("This settings link is for macOS only")
    subprocess.run(["/usr/bin/open", SETTINGS[permission]], check=True, timeout=15)


class Dialogs:
    def choose(self, title: str, message: str, options: list[str]) -> str | None:
        payload = {"title": title, "message": message, "options": options}
        native = files("ballz2thewall").joinpath("native")
        system = platform.system()
        if system == "Darwin":
            argv = ["/usr/bin/osascript", "-l", "JavaScript", str(native.joinpath("dialog.js")), json.dumps(payload)]
            result = subprocess.run(argv, capture_output=True, text=True, check=False)
        elif system == "Windows":
            argv = ["powershell.exe", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass",
                    "-File", str(native.joinpath("dialog.ps1"))]
            result = subprocess.run(argv, input=json.dumps(payload), capture_output=True, text=True,
                                    encoding="utf-8", check=False)
        else:
            if not sys.stdin.isatty():
                raise ValueError("Run ballz setup in an interactive terminal, or use --check for diagnostics.")
            print(f"\n{title}\n{message}")
            for index, option in enumerate(options, 1):
                print(f"  {index}. {option}")
            raw = input("Choose a number (Enter cancels): ").strip()
            return options[int(raw) - 1] if raw.isdigit() and 1 <= int(raw) <= len(options) else None
        if result.returncode:
            raise ValueError("Could not open the setup window. Reopen the installed Ballz2theWALL launcher.")
        try:
            data = json.loads(result.stdout.strip())
            choice = data.get("choice")
        except (ValueError, AttributeError):
            raise ValueError("Setup window returned an invalid response") from None
        if choice is not None and choice not in options:
            raise ValueError("Setup window returned an unknown choice")
        return choice

    def message(self, title: str, message: str) -> None:
        self.choose(title, message, ["OK"])


def guide_mac(dialogs: Dialogs) -> dict | None:
    status = mac_permissions()
    if status["responsible_app"] != "Terminal":
        raise ValueError("Use the installed Ballz2theWALL.command launcher. Mac access must belong to Terminal, "
                         "the app launching your agent—not this editor, SSH session or background service.")
    explanations = {
        "accessibility": ("Control apps", "Switch ON Terminal under Accessibility. This allows agent tools launched here to control apps."),
        "screen_recording": ("See your screen", "Allow Screen Recording for Terminal. If Mac asks to quit Terminal, do so and reopen Ballz2theWALL.command; setup resumes."),
        "full_disk_access": ("Access your files", "Switch ON Terminal under Full Disk Access. If absent, press + and choose Terminal in Applications → Utilities. Approve with your Mac password if asked, then reopen the launcher if required."),
    }
    for key, (title, explanation) in explanations.items():
        already = status.get(key) is True or (key == "full_disk_access" and status.get(key) == "protected_path_accessible")
        if already:
            continue
        choice = dialogs.choose(title, explanation, ["Continue", "Not now"])
        if choice != "Continue":
            return None
        request_mac(key)
        open_settings(key)
        while True:
            choice = dialogs.choose(title, explanation + "\n\nReturn here after enabling it.",
                                    ["Check again", "Open settings", "Not now"])
            if choice == "Open settings":
                open_settings(key)
                continue
            if choice != "Check again":
                return None
            status = mac_permissions()
            if status.get(key) is True or (key == "full_disk_access" and status.get(key) == "protected_path_accessible"):
                break
            if key == "full_disk_access" and status.get(key) == "unknown":
                confirmation = dialogs.choose(title, "Mac has no universal Full Disk Access check. "
                    "The protected test location is unavailable. Is Terminal visibly switched ON in Full Disk Access?",
                    ["Terminal is ON", "Open settings", "Not now"])
                if confirmation == "Terminal is ON":
                    status[key] = "user_confirmed_not_independently_verified"
                    break
                if confirmation == "Open settings":
                    open_settings(key)
                else:
                    return None
            else:
                dialogs.message("Permission not active yet", "Terminal does not have this access yet. "
                    "Switch it ON, or quit and reopen Terminal if macOS requests a restart.")
    choice = dialogs.choose("Connect to apps", "Next, macOS may ask whether Terminal can control Finder. "
        "Choose Allow. Other apps ask for their own approval when your agent first uses them.", ["Continue", "Not now"])
    if choice != "Continue":
        return None
    try:
        request_mac("automation")
    except ValueError:
        open_settings("automation")
        dialogs.message("Finder approval needed", "Enable Terminal → Finder in Automation, then reopen setup.")
        return None
    status["automation_finder"] = "verified_read_only_event"
    return status


def check_setup(state: Path) -> dict:
    return {"agents": discover_agents(), "permissions": permission_snapshot(),
            "activation": Activation(state).status(), "authentication": "not_read_or_tested",
            "scope": "native terminal launches; existing background agents unchanged"}


def wizard(state: Path, dialogs: Dialogs | None = None) -> int:
    dialogs = dialogs or Dialogs()
    controller = Activation(state)
    current = controller.status()
    if current["phase"] != "off":
        options = ["Start agent", "Turn OFF", "Close"] if current["phase"] == "on" else ["Recover / turn OFF", "Close"]
        choice = dialogs.choose("Ballz2theWALL — " + current["phase"].upper(),
            "Your selected agent uses expanded native settings.\n\n"
            "To turn OFF: close its agent window first. OFF restores previous settings for the next launch. "
            "It does not stop existing agents or revoke Mac permissions.", options)
        if choice in {"Turn OFF", "Recover / turn OFF"}:
            controller.disable()
            dialogs.message("Ballz2theWALL is OFF", "Previous agent settings restored. Your files and completed work are unchanged.")
            return 0
        if choice == "Start agent":
            return launch_interactive(current, state)
        return 130
    agents = discover_agents()
    if not agents:
        dialogs.message("Connect an agent first", "No compatible, configured Hermes, OpenAI Codex or Claude Code installation was found. "
            "Install and sign in to one of those agents first, then reopen Ballz2theWALL. "
            "No agent settings or permissions have been changed.")
        return 2
    labels = [f'{a["label"]}\n{a["home"]}' for a in agents]
    choice = labels[0] if len(labels) == 1 else dialogs.choose(
        "Choose your agent", "Choose the agent to connect. Only this profile will change.", labels)
    if choice is None:
        return 130
    selected = agents[labels.index(choice)]
    permissions = permission_snapshot()
    if permissions["platform"] == "Darwin":
        permissions = guide_mac(dialogs)
        if permissions is None:
            return 130
    elif permissions["platform"] == "Windows":
        if permissions.get("interactive_session") is not True:
            dialogs.message("Open setup on your desktop", "Open Ballz2theWALL from the Windows Start menu in your signed-in desktop session.")
            return 2
        if dialogs.choose("Windows access", "Normal terminal, file and desktop work uses your Windows account. "
            "Windows has no blanket permission switch for this. Administrator-only tasks still require a UAC-approved elevated launch. "
            "This installer does not disable UAC or change other accounts.", ["Continue", "Not now"]) != "Continue":
            return 130
    with Store(state / "controller").lock():
        atomic_write(state / "controller/setup.json", (json.dumps({"schema": 1, "agent": selected,
            "permissions": permissions, "authentication": "native agent handles sign-in"}, indent=2) + "\n").encode())
    choice = dialogs.choose("Ready to turn ON", f'{selected["label"]}\n{selected["home"]}\n\n'
        "ON applies the supported agent's expanded native settings. No extra Ballz execution popups. "
        "The agent keeps its own account and tools. Start it from this launcher for the Mac permissions you approved. "
        "Already-running agents do not change.", ["Turn ON", "Finish (OFF)"])
    if choice != "Turn ON":
        return 0 if choice == "Finish (OFF)" else 130
    active = controller.enable(selected["adapter"], Path(selected["home"]))
    choice = dialogs.choose("Ballz2theWALL is ON", "Open this launcher again to turn OFF. "
        "Close your agent window before switching OFF. Native settings restore; OS grants remain.", ["Start agent", "Finish"])
    return launch_interactive(active, state) if choice == "Start agent" else 0


def launch_interactive(record: dict, state: Path) -> int:
    from .cli import main
    # A GUI shortcut needs a real Windows console for the runtime, not stdin from
    # an installer pipe. CREATE_NEW_CONSOLE does not request Administrator access.
    argv = ["run", record["adapter"], "--home", record["home"], "--cwd", str(Path.home()), "--interactive"]
    if platform.system() == "Windows":
        subprocess.Popen([sys.executable, "-m", "ballz2thewall", *argv],
                         creationflags=subprocess.CREATE_NEW_CONSOLE, close_fds=True)
        return 0
    if platform.system() == "Darwin" and not terminal_responsible():
        raise ValueError("Start the agent using Ballz2theWALL.command in Terminal.")
    return main(argv)


def augment_path() -> None:
    """Finder/Start Menu do not necessarily inherit interactive shell PATH."""
    home = Path.home()
    known = [home / ".local/bin", home / ".cargo/bin", home / ".hermes/hermes-agent/venv/bin",
             Path("/opt/homebrew/bin"), Path("/usr/local/bin")]
    if os.name == "nt":
        local = Path(os.environ.get("LOCALAPPDATA", str(home / "AppData/Local")))
        known = [local / "hermes/hermes-agent/venv/Scripts", local / "Microsoft/WinGet/Links",
                 Path(os.environ.get("APPDATA", str(home / "AppData/Roaming"))) / "npm", home / ".local/bin"]
    current = os.environ.get("PATH", "")
    paths = [str(p) for p in known if p.is_dir() and str(p) not in current.split(os.pathsep)]
    if paths:
        os.environ["PATH"] = current + os.pathsep + os.pathsep.join(paths)
