#!/usr/bin/env python3
"""Build small double-click bundles around an immutable application wheel."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import stat
import zipfile
from pathlib import Path


def build(wheel: Path, output: Path) -> list[dict]:
    root = Path(__file__).resolve().parents[1]
    # Snapshot once: validation, hashes and both bundles must use identical bytes
    # even if a concurrent wheel build replaces the source file.
    wheel_bytes = wheel.read_bytes()
    if not wheel.name.startswith("ballz2thewall-") or not wheel.name.endswith(".whl") or len(wheel.name.split("-")) < 5:
        raise ValueError("Expected a ballz2thewall wheel filename")
    with zipfile.ZipFile(io.BytesIO(wheel_bytes)) as package:
        if package.testzip() is not None:
            raise ValueError("Wheel failed ZIP integrity validation")
        for required in ("ballz2thewall/native/dialog.ps1", "ballz2thewall/native/dialog.js", "ballz2thewall/onboarding.py"):
            if required not in package.namelist():
                raise ValueError(f"Wheel missing required setup component: {required}")
    version = wheel.name.split("-")[1]
    checksum = hashlib.sha256(wheel_bytes).hexdigest()
    output.mkdir(parents=True, exist_ok=True)
    results = []
    for platform, launcher in (("Windows", "Install-Windows.cmd"), ("Mac", "Install-Mac.command")):
        members = {launcher: (root / "installers" / launcher).read_bytes(),
                   "payload/" + wheel.name: wheel_bytes,
                   "payload/SHA256SUMS.json": (json.dumps({wheel.name: checksum}, indent=2) + "\n").encode(),
                   "LICENSE": (root / "LICENSE").read_bytes()}
        if platform == "Windows":
            members["windows/install.ps1"] = (root / "installers/windows/install.ps1").read_bytes()
        instructions = (
            f"Ballz2theWALL {version} - {platform} local alpha\n\n"
            f"1. Extract the entire ZIP.\n2. Double-click {launcher}.\n"
            "3. Follow setup. Approve requested OS prompts/settings yourself.\n"
            "4. Choose Turn ON when ready.\n\n"
            "Python installs privately and automatically. Internet access required on first install.\n"
            "An installed Hermes, OpenAI Codex, Claude Code or supported OpenClaw agent is required; it handles its own sign-in.\n"
            "OpenClaw requires Linux/WSL or Mac and a standard .openclaw home; native Windows is not supported.\n"
            "One agent found: selected automatically. Multiple profiles: choose one.\n"
            "Windows: reopen Ballz2theWALL from Start. Mac: Applications in your home folder, Ballz2theWALL.command.\n"
            "Close your agent window before turning OFF. OFF restores previous runtime settings; it does not stop\n"
            "existing processes, undo completed work or revoke OS permissions.\n\n"
            "This alpha installer is unsigned and not notarized. If your OS blocks it, do not expect the\n"
            "script to override that policy. Administrator and Mac privacy approvals remain yours.\n"
            "Mac: enable Terminal in Accessibility, Screen Recording and Full Disk Access. Finder Automation\n"
            "is requested separately. Other apps ask when used. Grants cover these Terminal launches, not\n"
            "unrelated background agents. Native Mac permission acceptance is still pending.\n"
        )
        members["START-HERE.txt"] = instructions.encode()
        destination = output / f"Ballz2theWALL-{version}-{platform}-Setup.zip"
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, content in members.items():
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | (0o755 if name.endswith(".command") else 0o644)) << 16
                archive.writestr(info, content, compress_type=zipfile.ZIP_DEFLATED)
        with zipfile.ZipFile(destination) as archive:
            if archive.testzip() is not None or archive.read("payload/" + wheel.name) != wheel_bytes:
                raise ValueError(f"Installer archive verification failed: {destination}")
            manifest = json.loads(archive.read("payload/SHA256SUMS.json"))
            if manifest.get(wheel.name) != hashlib.sha256(archive.read("payload/" + wheel.name)).hexdigest():
                raise ValueError(f"Installer payload checksum mismatch: {destination}")
            if platform == "Mac":
                if not (archive.getinfo(launcher).external_attr >> 16) & stat.S_IXUSR:
                    raise ValueError("Mac launcher is not executable")
        results.append({"path": str(destination), "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                        "bytes": destination.stat().st_size, "wheel_sha256": checksum})
    (output / "INSTALLERS.json").write_text(json.dumps(results, indent=2) + "\n")
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.wheel, args.output), indent=2))


if __name__ == "__main__":
    main()
