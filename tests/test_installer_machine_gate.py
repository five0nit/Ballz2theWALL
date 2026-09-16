"""Installer machine gates; extract validators only, never run installers."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def ready():
    return {"schema": 1, "status": "ready", "packages": {
        "cua-driver": {"installed": "0.28.1", "expected": "0.28.1", "importable": True},
        "mcp": {"installed": "1.30.0", "expected": "1.30.0", "importable": True}},
        "desktop_driver": {"command": "/private/desktop",
                           "version": "cua-driver 0.28.1", "status": "ready"},
        "errors": [], "scope": "dependencies_and_native_executable_only",
        "live_permissions": "not_tested"}


def windows_validate(values):
    from test_windows_installer import INSTALLER, native_path, powershell, ps_quote
    source = (
        "$ErrorActionPreference='Stop'; Set-StrictMode -Version Latest; "
        "$tokens=$null; $errors=$null; $ast=[Management.Automation.Language.Parser]::ParseFile("
        f"{ps_quote(native_path(INSTALLER))},[ref]$tokens,[ref]$errors); "
        "$fn=$ast.Find({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] "
        "-and $n.Name -eq 'ConvertFrom-MachineRuntime'},$true); Invoke-Expression $fn.Extent.Text; "
        f"$cases=ConvertFrom-Json -InputObject {ps_quote(json.dumps(values))}; "
        "$results=@(foreach ($value in $cases) { try { "
        "ConvertFrom-MachineRuntime $value | Out-Null; $true } catch { $false } }); "
        "ConvertTo-Json -InputObject $results -Compress"
    )
    result = powershell(source)
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def test_windows_validator_without_executing_installer():
    values = ["", "null", "[]", "{}", "not json", json.dumps(ready()),
              json.dumps({**ready(), "status": "unavailable"}),
              json.dumps({**ready(), "packages": {"cua-driver": {}, "mcp": {}}})]
    assert windows_validate(values) == [False, False, False, False, False, True, False, False]


def test_windows_machine_gate_precedes_shortcuts_and_receipt():
    text = (ROOT / "installers/windows/install.ps1").read_text()
    gate = text.index("$machineRuntimeJson = Invoke-Checked $python @('-I', '-m', 'ballz2thewall', 'machine', 'check')")
    assert text.index("$version = Invoke-Checked") < gate < text.index("$shortcutPath = $null")
    assert "ConvertFrom-MachineRuntime $machineRuntimeJson" in text
    assert "machine_runtime = $machineRuntime" in text
    assert "ConvertTo-Json -Depth 8" in text
    assert "ConvertFrom-MachineRuntime ($verifiedReceipt.machine_runtime" in text


@pytest.mark.parametrize("payload", [None, "", "not json", "[]", "null", "{}", "true",
                                    json.dumps({**ready(), "status": "blocked"}),
                                    json.dumps({**ready(), "schema": True}),
                                    json.dumps({**ready(), "packages": []}),
                                    json.dumps({**ready(), "packages": {"cua-driver": {}, "mcp": {}}}),
                                    json.dumps({**ready(), "desktop_driver": {}}),
                                    json.dumps({**ready(), "errors": ["broken"]}),
                                    json.dumps({**ready(), "live_permissions": "granted"}),
                                    json.dumps(ready())])
def test_mac_validator_accepts_only_complete_ready_evidence(payload):
    text = (ROOT / "installers/Install-Mac.command").read_text()
    gate = text.index('"$PYTHON" -I -m ballz2thewall machine check')
    assert text.index('"$PYTHON" -I -m ballz2thewall --version') < gate < text.index('mkdir -p "$HOME/Applications"')
    source = text.split("<<'MACHINE_CHECK_PY'\n", 1)[1].split("\nMACHINE_CHECK_PY", 1)[0]
    args = [sys.executable, "-I", "-c", source]
    if payload is not None:
        args.append(payload)
    result = subprocess.run(args, capture_output=True, text=True, timeout=5)
    assert (result.returncode == 0) == (payload == json.dumps(ready()))


def invalid_runtime_cases():
    """Keep status ready while corrupting independently required evidence."""
    cases = []
    missing = object()
    for package in ("cua-driver", "mcp"):
        for value in (missing, False, None, 0, 1, "true", [], {}):
            evidence = ready()
            if value is missing:
                del evidence["packages"][package]["importable"]
                label = "missing"
            else:
                evidence["packages"][package]["importable"] = value
                label = json.dumps(value)
            cases.append((f"{package}-importable-{label}", evidence))
    for value in (missing, "0.28.1", "unrelated-driver 99.99", "cua-driver 0.28.2",
                  "CUA-DRIVER 0.28.1", "cua-driver 0.28.1 ", True, ["cua-driver 0.28.1"]):
        evidence = ready()
        if value is missing:
            del evidence["desktop_driver"]["version"]
            label = "missing"
        else:
            evidence["desktop_driver"]["version"] = value
            label = json.dumps(value)
        cases.append((f"driver-version-{label}", evidence))
    return cases


INVALID_RUNTIME_CASES = invalid_runtime_cases()


@pytest.mark.parametrize("batch", [INVALID_RUNTIME_CASES[i:i + 6]
                                   for i in range(0, len(INVALID_RUNTIME_CASES), 6)])
def test_windows_validator_rejects_contradictory_readiness(batch):
    # Bounded batches stay below native Windows' command-line length limit.
    results = windows_validate([json.dumps(value) for _, value in batch])
    assert len(results) == len(batch)
    assert not any(results), [name for (name, _), accepted in zip(batch, results) if accepted]


@pytest.mark.parametrize("case", INVALID_RUNTIME_CASES, ids=[name for name, _ in INVALID_RUNTIME_CASES])
def test_mac_validator_rejects_contradictory_readiness(case):
    _, evidence = case
    text = (ROOT / "installers/Install-Mac.command").read_text()
    source = text.split("<<'MACHINE_CHECK_PY'\n", 1)[1].split("\nMACHINE_CHECK_PY", 1)[0]
    result = subprocess.run([sys.executable, "-I", "-c", source, json.dumps(evidence)],
                            capture_output=True, text=True, timeout=5)
    assert result.returncode != 0
    assert "Machine runtime check failed:" in result.stderr


@pytest.mark.parametrize("case", INVALID_RUNTIME_CASES, ids=[name for name, _ in INVALID_RUNTIME_CASES])
def test_receipt_assertion_rejects_contradictory_readiness(case):
    from test_windows_installer import assert_machine_runtime
    with pytest.raises((AssertionError, KeyError)):
        assert_machine_runtime(case[1])


def test_receipt_assertion_accepts_complete_readiness():
    from test_windows_installer import assert_machine_runtime
    assert_machine_runtime(ready())
