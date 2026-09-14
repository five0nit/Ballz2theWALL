import json
import os
import subprocess
import sys
import traceback
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ballz2thewall import credentials


@pytest.fixture
def stub_op(tmp_path, monkeypatch):
    """Exercise a real process without a vault, authentication, or shell."""
    executable = tmp_path / "op"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, sys\n"
        "pathlib.Path(os.environ['STUB_OP_ARGS']).write_text(json.dumps(sys.argv[1:]))\n"
        "sys.stdout.buffer.write(bytes.fromhex(os.environ.get('STUB_OP_OUTPUT', '')))\n"
        "sys.stderr.write(os.environ.get('STUB_OP_STDERR', ''))\n"
        "sys.exit(int(os.environ.get('STUB_OP_EXIT', '0')))\n"
    )
    executable.chmod(0o700)
    arguments = tmp_path / "arguments.json"
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setenv("STUB_OP_ARGS", str(arguments))
    monkeypatch.setenv("STUB_OP_EXIT", "0")
    monkeypatch.setenv("STUB_OP_STDERR", "")
    monkeypatch.setenv("STUB_OP_OUTPUT", b"stub-secret\n".hex())
    return arguments


def assert_redacted(call, *hidden):
    with pytest.raises(ValueError) as caught:
        call()
    rendered = "".join(traceback.format_exception(caught.value))
    assert str(caught.value)
    for value in hidden:
        assert value not in str(caught.value)
        # Traceback source lines can themselves include the test's literals.
        assert value not in "".join(traceback.format_exception_only(caught.value))
    assert caught.value.__suppress_context__ or caught.value.__context__ is None
    return rendered


def test_empty_list_is_valid():
    assert credentials.describe_bindings([]) == []
    assert credentials.resolve_bindings([]) == {}


def test_describe_is_json_safe_and_never_resolves(monkeypatch):
    forbidden = Mock(side_effect=AssertionError("dry-run resolution"))
    monkeypatch.setattr(credentials.os.environ, "get", forbidden)
    monkeypatch.setattr(credentials.subprocess, "run", forbidden)
    monkeypatch.setitem(sys.modules, "keyring", SimpleNamespace(get_password=forbidden))
    bindings = [
        "API_KEY=env:PRIVATE_SOURCE",
        "TOKEN=op:op://Private Vault/Private Item/field",
        "PASSWORD=keyring:private-service/private-account",
    ]
    metadata = credentials.describe_bindings(bindings)
    assert json.loads(json.dumps(metadata)) == [
        {"env": "API_KEY", "provider": "env"},
        {"env": "TOKEN", "provider": "op"},
        {"env": "PASSWORD", "provider": "keyring"},
    ]
    forbidden.assert_not_called()
    assert bindings[0] == "API_KEY=env:PRIVATE_SOURCE"


@pytest.mark.parametrize(
    "binding",
    [
        "",
        "RAW_PASSWORD",
        "=env:SOURCE",
        "1NAME=env:SOURCE",
        "BAD-NAME=env:SOURCE",
        " NAME=env:SOURCE",
        "NAME =env:SOURCE",
        "NÄME=env:SOURCE",
        "NAME=SOURCE",
        "NAME=:SOURCE",
        "NAME=env:",
        "NAME=ENV:SOURCE",
        "NAME=env:SOURCE=VALUE",
        "NAME=env:SOURCE:VALUE",
        "NAME=env:SOURCE VAR",
        "NAME=env:SOURCE\n",
        "NAME=env:SOURCE\x00",
        "NAME=env:1SOURCE",
        "NAME=env:SÖURCE",
        "NAME=shell:printf-secret",
        "NAME=file:/private/file",
        "NAME=browser:Chrome",
        "NAME=op:",
        "NAME=op:Vault/Item/field",
        "NAME=op:op://Vault/Item",
        "NAME=op:op://Vault//field",
        "NAME=op:op:///Item/field",
        "NAME=op:op://Vault/Item/field/",
        "NAME=op:op://Vault/Item/section/field/extra",
        "NAME=op:op://Vault/Item/field\r",
        "NAME=op:op://Vault/Item/field\x85",
        "NAME=keyring:",
        "NAME=keyring:service",
        "NAME=keyring:/account",
        "NAME=keyring:service/",
        "NAME=keyring:service/account\x00",
        "NAME=keyring:service/account\t",
        None,
        42,
    ],
)
@pytest.mark.parametrize("method", ["describe_bindings", "resolve_bindings"])
def test_malformed_binding_errors_do_not_echo(binding, method):
    hidden = [binding] if isinstance(binding, str) and binding else []
    assert_redacted(lambda: getattr(credentials, method)([binding]), *hidden)


@pytest.mark.parametrize("bindings", [None, "NAME=env:SOURCE", {"NAME": "env:SOURCE"}])
def test_malformed_container_is_generic(bindings):
    assert_redacted(lambda: credentials.describe_bindings(bindings))
    assert_redacted(lambda: credentials.resolve_bindings(bindings))


@pytest.mark.parametrize("later", ["BOUND=keyring:service/account", "INVALID_RAW_SECRET"])
def test_entire_list_validated_before_any_resolution(stub_op, monkeypatch, later):
    forbidden = Mock(side_effect=AssertionError("resolved before validation"))
    monkeypatch.setitem(sys.modules, "keyring", SimpleNamespace(get_password=forbidden))
    bindings = ["BOUND=op:op://Vault/Item/field", later]
    for method in (credentials.describe_bindings, credentials.resolve_bindings):
        assert_redacted(lambda: method(bindings), later, "op://Vault/Item/field")
    assert not stub_op.exists()
    forbidden.assert_not_called()


def test_env_uses_inherited_values_without_expansion_or_mutation(monkeypatch):
    value = "  unicode-雪; $(touch NEVER_CREATED) ' \" = : /  "
    monkeypatch.setenv("BALLZ_SOURCE", value)
    monkeypatch.setenv("BALLZ_DEST", "existing-destination")
    before = dict(os.environ)
    assert credentials.resolve_bindings(
        [
            "BALLZ_DEST=env:BALLZ_SOURCE",
            "SECOND=env:BALLZ_DEST",
            "_lower=env:BALLZ_SOURCE",
        ]
    ) == {"BALLZ_DEST": value, "SECOND": "existing-destination", "_lower": value}
    assert dict(os.environ) == before


@pytest.mark.parametrize("value", [None, "", "secret\n", "secret\r", "secret\t", "secret\x7f", "secret\x85"])
def test_missing_empty_or_control_env_value(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("PRIVATE_SOURCE", raising=False)
    else:
        monkeypatch.setenv("PRIVATE_SOURCE", value)
    assert_redacted(
        lambda: credentials.resolve_bindings(["DEST=env:PRIVATE_SOURCE"]), "PRIVATE_SOURCE", "secret"
    )


def test_op_uses_exact_argv_and_preserves_spaces(stub_op, monkeypatch, tmp_path):
    reference = "op://Vault/Item $(touch NEVER_CREATED); ' quote/section/field"
    value = "  secret-雪 = value  "
    monkeypatch.setenv("STUB_OP_OUTPUT", (value + "\n").encode().hex())
    monkeypatch.chdir(tmp_path)
    assert credentials.resolve_bindings([f"DEST=op:{reference}"]) == {"DEST": value}
    assert json.loads(stub_op.read_text()) == ["read", reference]
    assert not (tmp_path / "NEVER_CREATED").exists()


def test_op_without_appended_newline_is_unchanged(stub_op, monkeypatch):
    monkeypatch.setenv("STUB_OP_OUTPUT", b"  secret  ".hex())
    assert credentials.resolve_bindings(["DEST=op:op://Vault/Item/field"]) == {"DEST": "  secret  "}


@pytest.mark.parametrize(
    "output", [b"", b"\n", b"secret\n\n", b"secret\r\n", b"secret\x00\n", b"secret\t\n", b"\xff\n"]
)
def test_op_rejects_empty_control_or_invalid_utf8(stub_op, monkeypatch, output, capfd):
    monkeypatch.setenv("STUB_OP_OUTPUT", output.hex())
    assert_redacted(
        lambda: credentials.resolve_bindings(["DEST=op:op://Vault/Item/field"]),
        "secret",
        "op://Vault/Item/field",
    )
    assert capfd.readouterr() == ("", "")


def test_op_failure_never_exposes_output_or_stderr(stub_op, monkeypatch, capfd):
    monkeypatch.setenv("STUB_OP_EXIT", "9")
    monkeypatch.setenv("STUB_OP_STDERR", "MANAGER_PRIVATE_DIAGNOSTIC")
    monkeypatch.setenv("STUB_OP_OUTPUT", b"MANAGER_PRIVATE_SECRET\n".hex())
    rendered = assert_redacted(
        lambda: credentials.resolve_bindings(["DEST=op:op://Vault/Item/field"]),
        "MANAGER_PRIVATE_DIAGNOSTIC",
        "MANAGER_PRIVATE_SECRET",
        "op://Vault/Item/field",
    )
    assert "CalledProcessError" not in rendered
    assert capfd.readouterr() == ("", "")


def test_missing_op_is_generic(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    assert_redacted(
        lambda: credentials.resolve_bindings(["DEST=op:op://Vault/Item/field"]), "op://Vault/Item/field"
    )


def test_op_has_bounded_timeout_and_no_interactive_stdin(monkeypatch):
    argv = ["op", "read", "op://Vault/Item/field"]
    run = Mock(
        side_effect=subprocess.TimeoutExpired(
            argv,
            15,
            output=b"PRIVATE_OUTPUT",
            stderr=b"PRIVATE_ERROR",
        )
    )
    monkeypatch.setattr(credentials.subprocess, "run", run)
    rendered = assert_redacted(
        lambda: credentials.resolve_bindings(["DEST=op:op://Vault/Item/field"]),
        "PRIVATE_OUTPUT",
        "PRIVATE_ERROR",
        "op://Vault/Item/field",
    )
    assert "TimeoutExpired" not in rendered
    run.assert_called_once()
    args, kwargs = run.call_args
    assert args == (argv,)
    assert kwargs.get("shell", False) is False
    assert kwargs["stdin"] == subprocess.DEVNULL
    assert kwargs["stdout"] == subprocess.PIPE
    assert kwargs["stderr"] == subprocess.DEVNULL
    assert kwargs["check"] is True
    assert 0 < kwargs["timeout"] <= 30


def test_keyring_uses_only_selected_entry_and_preserves_value(monkeypatch):
    backend = SimpleNamespace(get_password=Mock(return_value="  fake-keyring-secret 雪  "))
    monkeypatch.setitem(sys.modules, "keyring", backend)
    assert credentials.resolve_bindings(["DEST=keyring:chosen service/person@example.test"]) == {
        "DEST": "  fake-keyring-secret 雪  ",
    }
    backend.get_password.assert_called_once_with("chosen service", "person@example.test")


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        42,
        b"secret",
        "secret\x00",
        "secret\n",
        "secret\r",
        "secret\t",
        "secret\x7f",
        "secret\x85",
        "secret\ud800",
    ],
)
def test_keyring_rejects_invalid_values(monkeypatch, value):
    monkeypatch.setitem(sys.modules, "keyring", SimpleNamespace(get_password=lambda *args: value))
    assert_redacted(
        lambda: credentials.resolve_bindings(["DEST=keyring:service/account"]), "secret", "service/account"
    )


def test_keyring_missing_optional_dependency(monkeypatch):
    monkeypatch.setitem(sys.modules, "keyring", None)
    assert_redacted(
        lambda: credentials.resolve_bindings(["DEST=keyring:private-service/private-account"]),
        "private-service",
        "private-account",
    )


def test_keyring_backend_exception_is_sanitized(monkeypatch):
    backend = SimpleNamespace(get_password=Mock(side_effect=RuntimeError("PRIVATE_BACKEND_SECRET")))
    monkeypatch.setitem(sys.modules, "keyring", backend)
    rendered = assert_redacted(
        lambda: credentials.resolve_bindings(["DEST=keyring:private-service/private-account"]),
        "PRIVATE_BACKEND_SECRET",
        "private-service",
        "private-account",
    )
    assert "RuntimeError" not in rendered


def test_mixed_providers_resolve_only_explicit_references(stub_op, monkeypatch):
    monkeypatch.setenv("SELECTED_SOURCE", "env-secret")
    monkeypatch.setenv("UNSELECTED_SOURCE", "unselected-secret")
    backend = SimpleNamespace(get_password=Mock(return_value="keyring-secret"))
    monkeypatch.setitem(sys.modules, "keyring", backend)
    assert credentials.resolve_bindings(
        [
            "A=env:SELECTED_SOURCE",
            "B=op:op://Vault/Item/field",
            "C=keyring:service/account",
        ]
    ) == {"A": "env-secret", "B": "stub-secret", "C": "keyring-secret"}
    backend.get_password.assert_called_once_with("service", "account")
