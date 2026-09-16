"""Bounded JSON transport; no process-global integer-policy changes."""
import json
import sys

import pytest


@pytest.mark.parametrize("exponent", [0, 400, 4299, 4300, 6500])
@pytest.mark.parametrize("sign", [1, -1])
def test_integer_roundtrip_and_global_policy_unchanged(exponent, sign):
    from ballz2thewall.wire_json import dumps, loads
    before = sys.get_int_max_str_digits()
    number = sign * 10 ** exponent
    data = {"timeout": number, "nested": [None, True, {"number": number}], "text": "quoted \"\\\n😀"}
    encoded = dumps(data, max_bytes=30000)
    assert loads(encoded, max_bytes=30000) == data
    assert sys.get_int_max_str_digits() == before
    token = ("-" if sign < 0 else "") + "1" + "0" * exponent
    assert '"timeout": ' + token in encoded or '"timeout":' + token in encoded
    assert loads(token, max_bytes=30000) == number


def test_ordinary_json_compatible():
    from ballz2thewall.wire_json import dumps, loads
    data = {"message": "héllo", "flags": [True, False, None], "n": 2.25, "empty": {}}
    assert json.loads(dumps(data)) == data
    assert loads(json.dumps(data)) == data


@pytest.mark.parametrize("operation", ["encode", "decode"])
def test_message_budget_is_bytes_not_timeout_cap(operation):
    from ballz2thewall.wire_json import dumps, loads
    with pytest.raises(ValueError, match="size limit"):
        if operation == "encode":
            dumps({"timeout": 10 ** 6500}, max_bytes=100)
        else:
            loads('{"timeout":1' + '0' * 6500 + '}', max_bytes=100)


def test_budget_includes_escaped_text_and_integer():
    from ballz2thewall.wire_json import dumps
    data = {"timeout": 10 ** 4300, "text": "\0" * 100}
    text = dumps(data, max_bytes=10000)
    assert len(text.encode()) > 4900
    with pytest.raises(ValueError, match="size limit"):
        dumps(data, max_bytes=len(text.encode()) - 1)
    assert dumps(data, max_bytes=len(text.encode())) == text


def test_oversized_integer_rejected_before_decimal_conversion():
    from ballz2thewall.wire_json import dumps
    with pytest.raises(ValueError, match="size limit"):
        dumps(1 << 1_000_000, max_bytes=100)


def test_fallback_preserves_json_types_and_rejects_cycles():
    from ballz2thewall.wire_json import dumps, loads
    data = {"huge": 10 ** 4300, "types": [False, None, {}, [], 1.5, '"sentinel"']}
    assert loads(dumps(data)) == data
    data["cycle"] = data
    with pytest.raises(ValueError):
        dumps(data)


@pytest.mark.parametrize("text", ['{"n":01}', '{"n":+1}', '{"n":1x}', '[1,]'])
def test_decoder_preserves_json_grammar(text):
    from ballz2thewall.wire_json import loads
    with pytest.raises(ValueError):
        loads(text)
