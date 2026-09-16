"""Release bundle integrity tests; never install software or request permissions."""
import hashlib
import importlib.util
import json
import stat
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_installers", ROOT / "scripts/build_installers.py")
assert SPEC is not None and SPEC.loader is not None
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


COMPONENTS = ("native/dialog.ps1", "native/dialog.js", "onboarding.py",
              "machine.py", "machine_jobs.py", "admin.py", "admin_jobs.py", "wire_json.py",
              "machine_bindings.py", "machine_check.py")


def make_wheel(tmp_path, missing=None, dependencies=None):
    wheel = tmp_path / "ballz2thewall-0.3.0a0.dev1-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as package:
        for name in COMPONENTS:
            if name != missing:
                package.writestr("ballz2thewall/" + name, "# isolated release fixture\n")
        dependencies = dependencies if dependencies is not None else ["cua-driver==0.28.1", "mcp==1.30.0"]
        package.writestr(
            "ballz2thewall-0.3.0a0.dev1.dist-info/METADATA",
            "Metadata-Version: 2.3\nName: ballz2thewall\nVersion: 0.3.0a0.dev1\n"
            + "".join(f"Requires-Dist: {dep}\n" for dep in dependencies) + "\n",
        )
    return wheel


def test_bundles_snapshot_wheel_once(tmp_path, monkeypatch):
    wheel = make_wheel(tmp_path)
    original = wheel.read_bytes()
    read_bytes = Path.read_bytes
    reads = []

    def changing_wheel(path):
        if path == wheel:
            reads.append(path)
            data = read_bytes(path)
            path.write_bytes(b"concurrent replacement")
            return data
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", changing_wheel)
    output = tmp_path / "release"
    results = builder.build(wheel, output)
    assert len(reads) == 1
    assert len(results) == 2
    assert json.loads((output / "INSTALLERS.json").read_text()) == results
    for result in results:
        path = Path(result["path"])
        assert result["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert result["bytes"] == path.stat().st_size
        with zipfile.ZipFile(path) as archive:
            assert archive.testzip() is None
            assert archive.read("payload/" + wheel.name) == original
            assert json.loads(archive.read("payload/SHA256SUMS.json")) == {
                wheel.name: hashlib.sha256(original).hexdigest(),
            }
            launcher = "Install-Mac.command" if "-Mac-" in path.name else "Install-Windows.cmd"
            assert archive.read(launcher) == (ROOT / "installers" / launcher).read_bytes()
            if launcher.endswith(".command"):
                assert archive.getinfo(launcher).external_attr >> 16 & stat.S_IXUSR
            else:
                assert archive.read("windows/install.ps1") == (ROOT / "installers/windows/install.ps1").read_bytes()


@pytest.mark.parametrize("missing", COMPONENTS)
def test_missing_setup_component_blocks_release(tmp_path, missing):
    wheel = make_wheel(tmp_path, missing)
    with pytest.raises(ValueError, match="required setup component"):
        builder.build(wheel, tmp_path / "release")
    assert not (tmp_path / "release").exists()


@pytest.mark.parametrize("dependencies", [[], ["cua-driver==0.28.1"], ["mcp==1.30.0"],
    ["cua-driver>=0.28.1", "mcp==1.30.0"], ["cua-driver==0.28.1", "mcp==1.29.0"],
    ['cua-driver==0.28.1; extra == "machine"', "mcp==1.30.0"]])
def test_machine_dependencies_must_be_unconditional_pins(tmp_path, dependencies):
    with pytest.raises(ValueError, match="dependency"):
        builder.build(make_wheel(tmp_path, dependencies=dependencies), tmp_path / "release")
    assert not (tmp_path / "release").exists()


def test_consumer_instructions(tmp_path):
    for result in builder.build(make_wheel(tmp_path), tmp_path / "release"):
        with zipfile.ZipFile(result["path"]) as archive:
            text = archive.read("START-HERE.txt").decode()
        for phrase in ("machine dependencies install automatically", "Start agent", "OFF disconnects",
                       "unrelated tools", "cancels managed in-flight operations", "experimental", "not tested"):
            assert phrase in text


def test_wrong_distribution_blocks_release(tmp_path):
    wheel = make_wheel(tmp_path)
    other = wheel.with_name("unrelated-0.2.0a2-py3-none-any.whl")
    wheel.rename(other)
    with pytest.raises(ValueError, match="ballz2thewall wheel"):
        builder.build(other, tmp_path / "release")
