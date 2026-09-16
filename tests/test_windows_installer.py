"""Native Windows installer gates; network installation is explicitly opt-in.

Run: B2W_WINDOWS_INSTALL_SMOKE=1 .venv/bin/python -m pytest -q tests/test_windows_installer.py
Scratch installations never launch the wizard or modify Start Menu / agent profiles.
The smoke receipt remains in the printed Windows temporary directory for inspection.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "installers/windows/install.ps1"
CMD = ROOT / "installers/Install-Windows.cmd"
POWERSHELL = shutil.which("powershell.exe") or (
    "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
    if Path("/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe").exists() else None
)


def assert_machine_runtime(evidence):
    assert evidence["schema"] == 1
    assert evidence["status"] == "ready"
    assert evidence["scope"] == "dependencies_and_native_executable_only"
    assert evidence["live_permissions"] == "not_tested"
    assert evidence["errors"] == []
    assert isinstance(evidence["packages"], dict)
    for name, pin in {"cua-driver": "0.28.1", "mcp": "1.30.0"}.items():
        assert evidence["packages"][name]["expected"] == pin
        assert evidence["packages"][name]["installed"] == pin
        assert evidence["packages"][name]["importable"] is True
    assert evidence["desktop_driver"]["status"] == "ready"
    assert evidence["desktop_driver"]["command"]
    assert evidence["desktop_driver"]["version"] == "cua-driver 0.28.1"


def ps_quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def native_path(path: Path) -> str:
    if not POWERSHELL or (os.name != "nt" and not shutil.which("wslpath")):
        pytest.skip("Native Windows PowerShell/WSL path translation is unavailable")
    if os.name == "nt":
        return str(path)
    return subprocess.check_output(["wslpath", "-w", str(path)], text=True).strip()


def local_path(path: str) -> Path:
    if os.name == "nt":
        return Path(path)
    return Path(subprocess.check_output(["wslpath", "-u", path], text=True).strip())


def powershell(code: str, *, timeout: int = 30) -> subprocess.CompletedProcess:
    if not POWERSHELL:
        pytest.skip("Native Windows PowerShell is unavailable")
    encoded = base64.b64encode(code.encode("utf-16le")).decode("ascii")
    return subprocess.run(
        [POWERSHELL, "-NoLogo", "-NoProfile", "-NonInteractive", "-STA", "-EncodedCommand", encoded],
        capture_output=True, text=True, timeout=timeout,
    )


def install(script: Path, root: Path, timeout: int = 30) -> subprocess.CompletedProcess:
    return powershell(
        f"& {ps_quote(native_path(script))} -InstallRoot {ps_quote(native_path(root))} "
        "-NonInteractive -NoLaunch -NoShortcut; exit $LASTEXITCODE", timeout=timeout,
    )


@pytest.fixture
def windows_scratch():
    result = powershell(
        "$p=Join-Path ([IO.Path]::GetTempPath()) ('ballz-installer-test-' + [Guid]::NewGuid()); "
        "New-Item -ItemType Directory -Path $p | Out-Null; $p"
    )
    assert result.returncode == 0, result.stderr
    scratch = local_path(result.stdout.strip())
    try:
        yield scratch
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def make_bundle(scratch: Path) -> Path:
    bundle = scratch / "bundle with spaces & apostrophe's"
    (bundle / "windows").mkdir(parents=True)
    shutil.copy2(INSTALLER, bundle / "windows/install.ps1")
    shutil.copy2(CMD, bundle / "Install-Windows.cmd")
    return bundle


def test_bootstrap_integrity_and_scope_contract():
    script = INSTALLER.read_text()
    cmd = CMD.read_text()
    assert "-NoProfile -STA -ExecutionPolicy Bypass" in cmd
    assert '%~dp0windows\\install.ps1' in cmd
    assert "Set-ExecutionPolicy" not in script
    assert "RunAs" not in script
    assert "0.12.5" in script
    for digest in (
        "4c4d49d8738847d9b71ba319e49a5688c93eac0fe6204b1df24e98528dddf39a",
        "724279317fee6e5fa8ad1908e4eba2bbe764ef1ece5b3f4597927b62b1fe562a",
    ):
        assert digest in script
    for contract in (
        "UV_PYTHON_INSTALL_DIR", "UV_CACHE_DIR", "--managed-python", "--no-config",
        "SHA256SUMS.json", "MessageBox", "ProgressBar", "DoEvents", "CreateShortcut",
        "-I -m ballz2thewall setup --gui", "profiles_changed = $false", "installer.lock",
    ):
        assert contract in script
    assert script.index("Wheel SHA-256 mismatch") < script.index("DownloadFileTaskAsync")
    assert script.index("requires Windows 10 or newer") < script.index("New-Item -ItemType Directory")
    assert "Invoke-Checked $python @('-I', '-m', 'ballz2thewall', '--version')" in script
    assert "Start-Process -FilePath $python -ArgumentList '-I -m ballz2thewall setup --gui'" in script


def test_missing_windows_toolchain_skips_before_path_conversion(monkeypatch):
    monkeypatch.setitem(globals(), "POWERSHELL", None)
    with pytest.raises(pytest.skip.Exception):
        native_path(INSTALLER)


def test_native_powershell_parser():
    result = powershell(
        "$tokens=$null; $errors=$null; "
        "[Management.Automation.Language.Parser]::ParseFile("
        f"{ps_quote(native_path(INSTALLER))}, [ref]$tokens, [ref]$errors) | Out-Null; "
        "$errors | ForEach-Object { $_.ToString() }; if ($errors.Count) {exit 1}; 'parser: PASS'"
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "parser: PASS" in result.stdout


@pytest.mark.parametrize("failure", ["missing", "empty", "manifest", "checksum", "multiple"])
def test_native_payload_fail_closed(windows_scratch, failure):
    bundle = make_bundle(windows_scratch)
    payload = bundle / "payload"
    if failure != "missing":
        payload.mkdir()
    if failure not in ("missing", "empty"):
        (payload / "ballz2thewall-0.1.1-py3-none-any.whl").write_bytes(b"not a wheel")
    if failure == "checksum":
        (payload / "SHA256SUMS.json").write_text(json.dumps({
            "ballz2thewall-0.1.1-py3-none-any.whl": "0" * 64,
        }))
    if failure == "multiple":
        (payload / "second.whl").write_bytes(b"also not a wheel")
    target = windows_scratch / "isolated product"
    result = install(bundle / "windows/install.ps1", target)
    assert result.returncode == 1, result.stdout + result.stderr
    expected = {
        "missing": "No release wheel or source pyproject.toml",
        "empty": "contains no wheel",
        "manifest": "checksum manifest is missing",
        "checksum": "Wheel SHA-256 mismatch",
        "multiple": "exactly one application wheel",
    }[failure]
    assert expected in result.stderr
    assert not (target / "runtime/bootstrap-0.12.5").exists()
    assert not (target / "runtime/install-receipt.json").exists()


def test_native_cmd_launcher(windows_scratch):
    bundle = make_bundle(windows_scratch)
    target = windows_scratch / "cmd isolated product"
    command = (
        f'""{native_path(bundle / "Install-Windows.cmd")}" '
        f'-InstallRoot "{native_path(target)}" -NonInteractive -NoLaunch -NoShortcut"'
    )
    stderr_file = windows_scratch / "cmd-stderr.txt"
    result = powershell(
        "$p=Start-Process -FilePath $env:ComSpec -ArgumentList "
        f"{ps_quote('/d /s /c ' + command)} -WorkingDirectory {ps_quote(native_path(windows_scratch))} "
        f"-RedirectStandardError {ps_quote(native_path(stderr_file))} -NoNewWindow -Wait -PassThru; exit $p.ExitCode"
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "No release wheel or source pyproject.toml" in stderr_file.read_text()


def test_native_argument_quoting():
    # Load only the quote function AST, without executing the installation script.
    values = ["space path", "apostrophe's & literal", 'double"quote', "C:\\trailing\\", ""]
    encoded_values = base64.b64encode(json.dumps(values).encode()).decode()
    code = (
        "$tokens=$null; $errors=$null; $ast=[Management.Automation.Language.Parser]::ParseFile("
        f"{ps_quote(native_path(INSTALLER))}, [ref]$tokens, [ref]$errors); "
        "$fn=$ast.Find({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] "
        "-and $n.Name -eq 'Quote-Argument'}, $true); Invoke-Expression $fn.Extent.Text; "
        f"$values=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded_values}')) | ConvertFrom-Json; "
        "@($values | ForEach-Object { Quote-Argument $_ }) | ConvertTo-Json -Compress"
    )
    result = powershell(code)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [
        '"space path"', '"apostrophe\'s & literal"', '"double\\"quote"', '"C:\\trailing\\\\"', '""',
    ]


def test_native_shortcut_in_scratch_only(windows_scratch):
    target = windows_scratch / "space & apostrophe's python.exe"
    shortcut = windows_scratch / "Ballz2theWALL.lnk"
    # Load only the production shortcut function; do not run the installer.
    result = powershell(
        "$tokens=$null; $errors=$null; $ast=[Management.Automation.Language.Parser]::ParseFile("
        f"{ps_quote(native_path(INSTALLER))}, [ref]$tokens, [ref]$errors); "
        "$fn=$ast.Find({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] "
        "-and $n.Name -eq 'Save-SetupShortcut'}, $true); Invoke-Expression $fn.Extent.Text; "
        f"Save-SetupShortcut {ps_quote(native_path(target))} {ps_quote(native_path(shortcut))} "
        f"{ps_quote(native_path(windows_scratch))}; "
        "$s=New-Object -ComObject WScript.Shell; "
        f"$c=$s.CreateShortcut({ps_quote(native_path(shortcut))}); "
        "@{target=$c.TargetPath; arguments=$c.Arguments; cwd=$c.WorkingDirectory} | ConvertTo-Json -Compress; "
        "[Runtime.InteropServices.Marshal]::FinalReleaseComObject($s) | Out-Null"
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert shortcut.exists()
    assert json.loads(result.stdout) == {
        "target": native_path(target), "arguments": "-I -m ballz2thewall setup --gui",
        "cwd": native_path(windows_scratch),
    }


def test_native_builtin_modules_survive_inherited_module_path(windows_scratch):
    bundle = make_bundle(windows_scratch)
    payload = bundle / "payload"
    payload.mkdir()
    name = "ballz2thewall-0.2.0a2-py3-none-any.whl"
    (payload / name).write_bytes(b"fixture")
    (payload / "SHA256SUMS.json").write_text(json.dumps({name: "0" * 64}))
    result = powershell(
        "$env:PSModulePath='C:\\missing-ballz-test-modules'; "
        f"& {ps_quote(native_path(bundle / 'windows/install.ps1'))} "
        f"-InstallRoot {ps_quote(native_path(windows_scratch / 'private'))} "
        "-NonInteractive -NoLaunch -NoShortcut; exit $LASTEXITCODE")
    assert result.returncode == 1
    assert "Wheel SHA-256 mismatch" in result.stderr
    assert "not recognized" not in result.stderr


@pytest.mark.skipif(os.getenv("B2W_WINDOWS_INSTALL_SMOKE") != "1", reason="Opt-in network/private-runtime smoke")
def test_native_actual_install_and_reinstall():
    result = powershell(
        "$p=Join-Path ([IO.Path]::GetTempPath()) ('ballz-guided-smoke-' + [Guid]::NewGuid()); "
        "New-Item -ItemType Directory -Path $p | Out-Null; $p"
    )
    assert result.returncode == 0, result.stderr
    scratch = local_path(result.stdout.strip())
    bundle = make_bundle(scratch)
    payload = bundle / "payload"
    payload.mkdir()
    import sys
    build = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(payload)],
        cwd=ROOT, text=True, capture_output=True, timeout=120,
    )
    assert build.returncode == 0, build.stdout + build.stderr
    wheels = list(payload.glob("*.whl"))
    assert len(wheels) == 1
    (payload / "SHA256SUMS.json").write_text(json.dumps({
        wheels[0].name: hashlib.sha256(wheels[0].read_bytes()).hexdigest(),
    }))
    root = scratch / "isolated product & private runtime"
    state = root / "state/keep.json"
    state.parent.mkdir(parents=True)
    state.write_text('{"preserve": true}')
    snapshot = (
        "@{ user_path=[Environment]::GetEnvironmentVariable('PATH','User'); "
        "machine_path=[Environment]::GetEnvironmentVariable('PATH','Machine'); "
        "shortcut=Test-Path (Join-Path ([Environment]::GetFolderPath('Programs')) 'Ballz2theWALL.lnk') } "
        "| ConvertTo-Json -Compress"
    )
    before = powershell(snapshot)
    receipt = {}
    for attempt in range(2):
        result = install(bundle / "windows/install.ps1", root, timeout=570)
        (scratch / f"attempt-{attempt + 1}.txt").write_text(result.stdout + result.stderr)
        assert result.returncode == 0, result.stdout + result.stderr
        receipt = json.loads((root / "runtime/install-receipt.json").read_text(encoding="utf-8-sig"))
        assert receipt["status"] == "installed"
        assert receipt["profiles_changed"] is False
        assert receipt["shortcut"] is None
        assert receipt["uv_version"] == "0.12.5"
        assert_machine_runtime(receipt["machine_runtime"])
        assert state.read_text() == '{"preserve": true}'
    # Exercise the real source fallback too, reusing only the private runtime.
    source = scratch / "source checkout"
    source.mkdir()
    for name in ("pyproject.toml", "README.md", "LICENSE"):
        shutil.copy2(ROOT / name, source / name)
    shutil.copytree(ROOT / "src", source / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (source / "installers/windows").mkdir(parents=True)
    shutil.copy2(INSTALLER, source / "installers/windows/install.ps1")
    source_result = install(source / "installers/windows/install.ps1", root, timeout=570)
    (scratch / "source-install.txt").write_text(source_result.stdout + source_result.stderr)
    assert source_result.returncode == 0, source_result.stdout + source_result.stderr
    source_receipt = json.loads((root / "runtime/install-receipt.json").read_text(encoding="utf-8-sig"))
    assert source_receipt["package"] == native_path(source)
    assert source_receipt["package_sha256"] is None
    assert_machine_runtime(source_receipt["machine_runtime"])
    assert state.read_text() == '{"preserve": true}'
    after = powershell(snapshot)
    assert before.returncode == after.returncode == 0
    assert json.loads(before.stdout) == json.loads(after.stdout)
    python = root / "runtime/venv/Scripts/python.exe"
    check = powershell(
        f"& {ps_quote(native_path(python))} -I -c "
        + ps_quote("import ballz2thewall, json, sys; print(json.dumps({'file': ballz2thewall.__file__, 'version': sys.version}))")
    )
    assert check.returncode == 0, check.stderr
    provenance = json.loads(check.stdout)
    assert "site-packages" in provenance["file"]
    assert provenance["version"].startswith("3.11.")
    assert (root / "runtime/python").is_dir()
    assert (root / "runtime/cache").is_dir()
    (scratch / "verification.json").write_text(json.dumps({
        "status": "passed", "install_and_reinstall": True, "source_install": True, "preserved_state": True,
        "path_and_shortcut_unchanged": True, "provenance": provenance, "wheel_receipt": receipt,
        "source_receipt": source_receipt,
    }, indent=2))
    print(f"Native Windows smoke receipts: {scratch}")
