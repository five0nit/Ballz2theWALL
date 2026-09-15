"""API-boundary tests, not a claim that macOS granted a permission."""
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from ballz2thewall import onboarding as ob


def status(**overrides):
    return {"platform": "Darwin", "responsible_app": "Terminal", "accessibility": False,
            "screen_recording": False, "full_disk_access": "permission_needed", **overrides}


class Answers:
    def __init__(self, choices):
        self.choices = iter(choices)
        self.messages = []
    def choose(self, title, message, options):
        self.messages.append(message)
        choice = next(self.choices)
        assert choice in options or choice is None
        return choice
    def message(self, title, message):
        self.messages.append(message)


def test_mac_wrong_responsible_app_never_requests(monkeypatch):
    monkeypatch.setattr(ob, "mac_permissions", lambda: status(responsible_app="unsupported_launcher"))
    with pytest.raises(ValueError, match="launcher"):
        ob.guide_mac(Answers([]))


def test_mac_not_now_does_not_request(monkeypatch):
    monkeypatch.setattr(ob, "mac_permissions", status)
    monkeypatch.setattr(ob, "request_mac", lambda p: pytest.fail("not authorized"))
    assert ob.guide_mac(Answers(["Not now"])) is None


def test_native_mac_retry_requires_real_check(monkeypatch):
    checks = iter([status(), status(accessibility=True),
                   status(accessibility=True, screen_recording=True),
                   status(accessibility=True, screen_recording=True, full_disk_access="protected_path_accessible")])
    monkeypatch.setattr(ob, "mac_permissions", lambda: next(checks))
    requests, settings = [], []
    monkeypatch.setattr(ob, "request_mac", requests.append)
    monkeypatch.setattr(ob, "open_settings", settings.append)
    dialogs = Answers(["Continue", "Check again", "Continue", "Check again", "Continue", "Check again", "Continue"])
    result = ob.guide_mac(dialogs)
    assert requests == ["accessibility", "screen_recording", "full_disk_access", "automation"]
    assert settings == requests[:-1]
    assert result["automation_finder"] == "verified_read_only_event"


def test_unknown_fda_explicit_user_confirmation_not_verified(monkeypatch):
    monkeypatch.setattr(ob, "mac_permissions", lambda: status(accessibility=True, screen_recording=True, full_disk_access="unknown"))
    monkeypatch.setattr(ob, "request_mac", lambda _: None)
    monkeypatch.setattr(ob, "open_settings", lambda _: None)
    result = ob.guide_mac(Answers(["Continue", "Check again", "Terminal is ON", "Continue"]))
    assert result["full_disk_access"] == "user_confirmed_not_independently_verified"


def test_automation_denial_not_setup_success(monkeypatch):
    monkeypatch.setattr(ob, "mac_permissions", lambda: status(accessibility=True, screen_recording=True, full_disk_access="protected_path_accessible"))
    def denied(_):
        raise ValueError("Denied")
    monkeypatch.setattr(ob, "request_mac", denied)
    monkeypatch.setattr(ob, "open_settings", lambda _: None)
    assert ob.guide_mac(Answers(["Continue"])) is None


def test_mac_dialog_json_is_not_code(monkeypatch):
    monkeypatch.setattr(ob.platform, "system", lambda: "Darwin")
    calls = []
    def run(argv, **kwargs):
        calls.append(argv)
        payload = json.loads(argv[-1])
        return SimpleNamespace(returncode=0, stdout=json.dumps({"choice": payload["options"][0]}))
    monkeypatch.setattr(ob.subprocess, "run", run)
    text = "quote \"; do shell script \"anything \" / newline\n is data"
    assert ob.Dialogs().choose("Title", text, ["OK"]) == "OK"
    assert json.loads(calls[0][-1])["message"] == text
    assert calls[0][1:3] == ["-l", "JavaScript"]


def test_mac_requests_impossible_on_other_platform(monkeypatch):
    monkeypatch.setattr(ob.platform, "system", lambda: "Linux")
    with pytest.raises(ValueError, match="Terminal"):
        ob.request_mac("accessibility")


def test_mac_installer_isolation_and_preflight(tmp_path):
    script = Path(__file__).resolve().parents[1] / "installers/Install-Mac.command"
    content = script.read_text()
    assert subprocess.run(["bash", "-n", str(script)], capture_output=True).returncode == 0
    assert '"$PYTHON" -m' not in content
    assert '"$PYTHON" - ' not in content
    assert " -I -m ballz2thewall setup --gui" in content
    for check in ("sw_vers", "Unsupported Mac processor", "Incomplete package", "Missing package", "cancel button"):
        assert content.index(check) < content.index('mkdir -p "$ROOT"')
    assert content.index("Runtime download checksum mismatch") < content.index("/usr/bin/tar -xzf")
    # Execute the real launcher-writer payload, including -I, with poisoned
    # current-directory/PYTHONPATH imports and a shell-metacharacter path.
    writer = content.split('"$LAUNCHER" <<\'PY\'\n', 1)[1].split("\nPY", 1)[0]
    (tmp_path / "pathlib.py").write_text("raise RuntimeError('untrusted import')")
    launcher = tmp_path / "launcher.command"
    python = str(tmp_path / "space & apostrophe's" / "python")
    result = subprocess.run([sys.executable, "-I", "-", python, str(launcher)], input=writer,
                            text=True, capture_output=True, cwd=tmp_path,
                            env={**os.environ, "PYTHONPATH": str(tmp_path)})
    assert result.returncode == 0, result.stderr
    import shlex
    assert shlex.split(launcher.read_text().split("exec ")[1]) == [
        python, "-I", "-m", "ballz2thewall", "setup", "--gui",
    ]
