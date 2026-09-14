"""Validate an explicit CDP base endpoint and fetch whitelisted version metadata.

This module does not discover hosts, enumerate tabs, attach to a browser, persist
cookies, or return debugger URLs. A caller must supply the endpoint explicitly.
Only the Python standard library is used.
"""

from __future__ import annotations

import http.client
import ipaddress
import json
import math
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

__all__ = ["validate_cdp_url", "probe_cdp"]

_MAX_URL_LENGTH = 4096
_MAX_RESPONSE_BYTES = 64 * 1024
_INVALID_URL = "Invalid CDP endpoint URL."
_INVALID_RESPONSE = "Invalid CDP version response."
_HTTP_ERROR = "CDP endpoint returned an HTTP error."
_REDIRECT_ERROR = "CDP endpoint redirected; redirects are not allowed."
_CONNECTION_ERROR = "Unable to connect to CDP endpoint."
_TIMEOUT_ERROR = "CDP probe timed out."
_SIZE_ERROR = "CDP response is too large."

_HOST_LABEL = re.compile(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?")
_PATH_SEGMENT = re.compile(r"[A-Za-z0-9._~-]+")
# Product/version strings, not arbitrary server text, URLs, or cookie values.
_BROWSER_VERSION = re.compile(r"[A-Za-z][A-Za-z0-9 ._+-]{0,63}/[0-9][A-Za-z0-9._+-]{0,63}")
_PROTOCOL_VERSION = re.compile(r"[0-9]{1,4}(?:\.[0-9]{1,4}){1,3}")


def validate_cdp_url(url: str) -> str:
    """Return a canonical HTTP(S) base URL or raise a generic ``ValueError``.

    Conventions:
    * Require an explicit ``http://`` or ``https://`` authority, at most 4096
      printable ASCII characters. Do not trim whitespace or repair bad input.
    * Accept DNS names (including single-label LAN names and Tailscale DNS),
      strict dotted-decimal IPv4, and bracketed IPv6. DNS labels are 1--63
      letters/digits/hyphens, without edge hyphens; the name is at most 253
      characters excluding an optional final dot. Unicode names must be supplied
      as ASCII IDNA names. Legacy numeric IPv4 spellings and IPv6 zone IDs are
      rejected. No address-range restriction or DNS/network lookup is performed.
    * An optional decimal port must be in 1--65535; no default port is injected.
    * Reject userinfo, backslashes, percent escapes, query and fragment markers
      (even empty ``?`` or ``#``), controls, whitespace, and non-ASCII input.
    * The path is a literal reverse-proxy base prefix, not a discovery resource.
      Each segment must contain only ASCII letters/digits or ``-._~`` and must
      not be ``.`` or ``..``. Empty/interior double-slash segments are forbidden.
      One trailing slash is allowed and removed, including the root slash.
      The probe appends ``/json/version``: ``http://host/cdp/`` becomes a request
      to ``http://host/cdp/json/version``. It never applies ``urljoin`` semantics.

    Scheme and authority are lowercased; path case and port spelling are kept.
    Invalid input is never included in the exception message.
    """
    if (
        not isinstance(url, str)
        or not url
        or len(url) > _MAX_URL_LENGTH
        or any(ord(char) <= 32 or ord(char) >= 127 for char in url)
        or any(char in url for char in "@\\%?#")
    ):
        raise ValueError(_INVALID_URL)

    try:
        parsed = urlsplit(url)
    except ValueError:
        raise ValueError(_INVALID_URL) from None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(_INVALID_URL)

    authority = parsed.netloc
    if authority.startswith("["):
        match = re.fullmatch(r"\[([0-9A-Fa-f:.]+)\](?::([0-9]+))?", authority)
        if match is None:
            raise ValueError(_INVALID_URL)
        host, port = match.groups()
        try:
            ipaddress.IPv6Address(host)
        except ValueError:
            raise ValueError(_INVALID_URL) from None
    else:
        match = re.fullmatch(r"([^:]+)(?::([0-9]+))?", authority)
        if match is None:
            raise ValueError(_INVALID_URL)
        host, port = match.groups()
        try:
            ipaddress.IPv4Address(host)
        except ValueError:
            dns_name = host.removesuffix(".")
            labels = dns_name.split(".")
            if (
                not dns_name
                or len(dns_name) > 253
                or any(_HOST_LABEL.fullmatch(label) is None for label in labels)
                # Do not pass inet_aton-style aliases (127.1, octal, hex, integer)
                # or malformed dotted IPv4 through to the resolver as DNS names.
                or re.fullmatch(r"(?:[0-9]+|0[xX][0-9a-fA-F]+)", labels[-1])
            ):
                raise ValueError(_INVALID_URL) from None

    if port is not None and not 1 <= int(port) <= 65535:
        raise ValueError(_INVALID_URL)

    path = parsed.path
    if path == "/":
        path = ""
    elif path:
        if not path.startswith("/"):
            raise ValueError(_INVALID_URL)
        path = path.removesuffix("/")
        if any(
            segment in {".", ".."} or _PATH_SEGMENT.fullmatch(segment) is None
            for segment in path[1:].split("/")
        ):
            raise ValueError(_INVALID_URL)
    return f"{parsed.scheme}://{authority.lower()}{path}"


class _NoRedirect(HTTPRedirectHandler):
    """Keep even same-host and same-scheme redirects from issuing a request."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _failure(error: str) -> dict[str, bool | str | None]:
    return {"connected": False, "browser": None, "protocol_version": None, "error": error}


def _reject_constant(_value: str):
    raise ValueError(_INVALID_RESPONSE)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(_INVALID_RESPONSE)
        result[key] = value
    return result


def probe_cdp(url: str, timeout: float = 3) -> dict[str, bool | str | None]:
    """GET only ``<validated base>/json/version`` and return four safe fields.

    Exactly ``connected``, ``browser``, ``protocol_version``, and ``error`` are
    returned. Success requires HTTP 200 and a UTF-8 JSON object containing a
    Browser product/version string and a numeric dotted Protocol-Version string.
    Browser product names are 1--64 ASCII letters/digits/spaces/``._+-`` starting
    with a letter; their slash-separated version is 1--64 letters/digits/``._+-``
    starting with a digit. Protocol versions have 2--4 numeric components of
    1--4 digits each. Other JSON fields and all response headers are discarded.
    Missing or invalid metadata, duplicate keys, nonstandard JSON constants, and
    compressed responses fail closed. Errors are fixed strings, never exception
    text, response bodies, URLs, headers, credentials, or debugger details.

    All redirects are refused. A private opener with ``ProxyHandler({})`` ignores
    ALL environment/system proxies and any installed global opener. No cookie or
    authentication handlers are installed. HTTPS uses normal certificate checks.
    The response body is limited to 64 KiB, including chunked/no-length responses;
    no decompression is performed. Only one explicit endpoint request is made.

    ``timeout`` is a positive finite int/float in seconds (booleans excluded).
    It is the standard-library connection/read socket timeout, not a hard total
    deadline: OS DNS resolution and a peer trickling bytes may take longer.
    Invalid endpoints or timeouts fail before any network activity.
    """
    try:
        base = validate_cdp_url(url)
    except ValueError:
        return _failure(_INVALID_URL)

    try:
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise ValueError
        duration = float(timeout)
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        return _failure("Invalid CDP probe timeout.")

    opener = build_opener(ProxyHandler({}), _NoRedirect())
    request = Request(
        base + "/json/version",
        headers={"Accept": "application/json", "Accept-Encoding": "identity"},
        method="GET",
    )
    try:
        with opener.open(request, timeout=duration) as response:
            if response.status != 200:
                return _failure(_HTTP_ERROR)
            if response.headers.get("Content-Encoding", "").strip().lower() not in {"", "identity"}:
                return _failure(_INVALID_RESPONSE)
            lengths = response.headers.get_all("Content-Length", [])
            expected_length = None
            if lengths:
                if len(lengths) != 1 or re.fullmatch(r"[0-9]+", lengths[0]) is None:
                    return _failure(_INVALID_RESPONSE)
                # Bound integer parsing too, without trusting a malicious header.
                significant_digits = lengths[0].lstrip("0") or "0"
                if len(significant_digits) > 5:
                    return _failure(_SIZE_ERROR)
                expected_length = int(significant_digits)
                if expected_length > _MAX_RESPONSE_BYTES:
                    return _failure(_SIZE_ERROR)
            body = response.read(_MAX_RESPONSE_BYTES + 1)
            if len(body) > _MAX_RESPONSE_BYTES:
                return _failure(_SIZE_ERROR)
            if expected_length is not None and len(body) != expected_length:
                return _failure(_INVALID_RESPONSE)
    except HTTPError as error:
        redirected = 300 <= error.code < 400
        error.close()
        return _failure(_REDIRECT_ERROR if redirected else _HTTP_ERROR)
    except TimeoutError:
        return _failure(_TIMEOUT_ERROR)
    except URLError as error:
        return _failure(_TIMEOUT_ERROR if isinstance(error.reason, TimeoutError) else _CONNECTION_ERROR)
    except http.client.IncompleteRead:
        return _failure(_INVALID_RESPONSE)
    except (OSError, http.client.HTTPException, ValueError, OverflowError):
        return _failure(_CONNECTION_ERROR)

    try:
        metadata = json.loads(
            body.decode("utf-8"), parse_constant=_reject_constant, object_pairs_hook=_unique_object
        )
    except (UnicodeError, ValueError, RecursionError):
        return _failure(_INVALID_RESPONSE)
    if not isinstance(metadata, dict):
        return _failure(_INVALID_RESPONSE)
    browser = metadata.get("Browser")
    protocol = metadata.get("Protocol-Version")
    if (
        not isinstance(browser, str)
        or _BROWSER_VERSION.fullmatch(browser) is None
        or not isinstance(protocol, str)
        or _PROTOCOL_VERSION.fullmatch(protocol) is None
    ):
        return _failure(_INVALID_RESPONSE)
    return {"connected": True, "browser": browser, "protocol_version": protocol, "error": None}
