"""Bounded JSON with exact integers, independent of Python's digit policy.

Use the standard JSON grammar/string escaping, but convert decimal integers in
small chunks. Message-byte limits remain transport limits, not timeout caps.
Never change sys.set_int_max_str_digits: other threads share that policy.
"""
from __future__ import annotations

import json

DEFAULT_MAX_BYTES = 2 * 1024 * 1024
_BASE = 1_000_000_000


def _integer(text: str) -> int:
    negative = text.startswith("-")
    digits = text[1:] if negative else text
    value = 0
    for offset in range(0, len(digits), 9):
        chunk = digits[offset:offset + 9]
        value = value * (10 ** len(chunk)) + int(chunk)
    return -value if negative else value


def loads(data: str | bytes | bytearray, *, max_bytes: int = DEFAULT_MAX_BYTES):
    size = len(data.encode("utf-8")) if isinstance(data, str) else len(data)
    if size > max_bytes:
        raise ValueError("JSON message exceeds size limit")
    try:
        return json.loads(data, parse_int=_integer)
    except RecursionError as exc:
        raise ValueError("JSON nesting exceeds decoder limit") from exc


def dumps(value, *, max_bytes: int = DEFAULT_MAX_BYTES) -> str:
    """Encode JSON values with string keys; enforce escaped ASCII wire size."""
    parts: list[str] = []
    size = 0
    ancestors: set[int] = set()

    def emit(text: str) -> None:
        nonlocal size
        size += len(text)  # All emitted text is ASCII (ensure_ascii=True).
        if size > max_bytes:
            raise ValueError("JSON message exceeds size limit")
        parts.append(text)

    def encode(item, depth=0):
        if depth > 64:
            raise ValueError("JSON nesting exceeds encoder limit")
        if item is None or isinstance(item, (str, bool, float)):
            if isinstance(item, str) and len(item) > max_bytes - size:
                raise ValueError("JSON message exceeds size limit")
            emit(json.dumps(item, ensure_ascii=True, allow_nan=False))
        elif isinstance(item, int):
            number = abs(item)
            # Decimal takes at least one byte per four binary digits. Reject
            # obviously oversized values before the repeated division work.
            if number.bit_length() > (max_bytes - size) * 4:
                raise ValueError("JSON message exceeds size limit")
            if item < 0:
                emit("-")
            chunks = []
            while number >= _BASE:
                number, remainder = divmod(number, _BASE)
                chunks.append(remainder)
            emit(str(number))
            for chunk in reversed(chunks):
                emit(f"{chunk:09d}")
        elif isinstance(item, (dict, list, tuple)):
            identity = id(item)
            if identity in ancestors:
                raise ValueError("Circular JSON value")
            ancestors.add(identity)
            try:
                mapping = isinstance(item, dict)
                emit("{" if mapping else "[")
                for index, entry in enumerate(item):
                    if index:
                        emit(",")
                    if mapping:
                        if not isinstance(entry, str):
                            raise TypeError("JSON object keys must be strings")
                        encode(entry, depth + 1)
                        emit(":")
                        encode(item[entry], depth + 1)
                    else:
                        encode(entry, depth + 1)
                emit("}" if mapping else "]")
            finally:
                ancestors.remove(identity)
        else:
            raise TypeError(f"Object of type {type(item).__name__} is not JSON serializable")

    encode(value)
    return "".join(parts)
