"""Invalid smoke invocations must stop before touching native runtimes."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "machine_native_smoke.py"


@pytest.mark.parametrize("args,code", [([], 2), (["--help"], 0), (["--unknown"], 2)])
def test_argument_validation_precedes_native_work(tmp_path, args, code):
    # Shadow the application under a non-isolated Python invocation. Any import
    # proves argument parsing ran too late; no native dependencies are needed.
    (tmp_path / "ballz2thewall.py").write_text(
        'raise RuntimeError("NATIVE_IMPORT_MUST_NOT_RUN")\n', encoding="utf-8"
    )
    (tmp_path / "mcp.py").write_text(
        'raise RuntimeError("NATIVE_IMPORT_MUST_NOT_RUN")\n', encoding="utf-8"
    )
    env = dict(os.environ, PYTHONPATH=str(tmp_path), PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *args], cwd=tmp_path, env=env,
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == code, result.stderr
    assert "usage:" in result.stdout + result.stderr
    assert "Traceback" not in result.stderr
    assert "NATIVE_IMPORT_MUST_NOT_RUN" not in result.stderr


@pytest.mark.parametrize('fail_inside', [False, True])
def test_scratch_controller_public_activation_and_off(tmp_path, fail_inside):
    import importlib.util

    from ballz2thewall.onboarding import Activation
    spec = importlib.util.spec_from_file_location('native_smoke', SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        with module.scratch_controller(tmp_path) as (state, record):
            assert Activation(state).status()['phase'] == 'on'
            assert record['machine_access'] is True
            if fail_inside:
                raise RuntimeError('fixture probe failed')
    except RuntimeError as exc:
        assert str(exc) == 'fixture probe failed'
    assert Activation(tmp_path / 'state').status()['phase'] == 'off'
    assert not (tmp_path / 'controller-agent' / 'config.yaml').exists()
