"""Offline CDP probe tests: every HTTP request uses a real loopback server."""

from __future__ import annotations

import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from ballz2thewall.browser import probe_cdp, validate_cdp_url

VERSION = {"Browser": "Chrome/123.0.6312.59", "Protocol-Version": "1.3"}
BODY_LIMIT = 64 * 1024
RESULT_KEYS = {"connected", "browser", "protocol_version", "error"}
SECRET = "sensitive-debugger-cookie-tab-marker"


@pytest.fixture
def http_server():
    """Run only explicit 127.0.0.1 servers; retain requests for no-follow checks."""
    running = []

    def start(
        *,
        body=None,
        status=200,
        headers=None,
        content_length=True,
        header_delay=0,
        body_delay=0,
        responder=None,
    ):
        payload = json.dumps(VERSION).encode() if body is None else body
        requests = []

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format, *args):
                pass

            def do_CONNECT(self):
                requests.append(
                    {"method": self.command, "path": self.path, "headers": dict(self.headers)}
                )
                self.send_error(502)

            def do_GET(self):
                requests.append(
                    {"method": self.command, "path": self.path, "headers": dict(self.headers)}
                )
                try:
                    if responder is not None:
                        responder(self)
                        return
                    if header_delay:
                        time.sleep(header_delay)
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Connection", "close")
                    extra_headers = headers or {}
                    if content_length and "Content-Length" not in extra_headers:
                        self.send_header("Content-Length", str(len(payload)))
                    for name, value in extra_headers.items():
                        self.send_header(name, value)
                    self.end_headers()
                    if body_delay:
                        time.sleep(body_delay)
                    self.wfile.write(payload)
                    self.close_connection = True
                except (BrokenPipeError, ConnectionResetError):
                    # A timeout or a size rejection deliberately closes the client.
                    pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(
            target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        )
        thread.start()
        running.append((server, thread))
        return SimpleNamespace(
            url=f"http://127.0.0.1:{server.server_port}", requests=requests
        )

    yield start
    for server, thread in reversed(running):
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()


def assert_failure(result, expected_error=None):
    assert set(result) == RESULT_KEYS
    assert result["connected"] is False
    assert result["browser"] is None
    assert result["protocol_version"] is None
    assert isinstance(result["error"], str) and result["error"]
    assert SECRET not in json.dumps(result)
    if expected_error is not None:
        assert result["error"] == expected_error


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://localhost:9222", "http://localhost:9222"),
        ("HTTP://LOCALHOST:9222/", "http://localhost:9222"),
        ("https://Example.COM", "https://example.com"),
        ("https://example.com:443/cdp/", "https://example.com:443/cdp"),
        ("http://192.168.1.12:9222", "http://192.168.1.12:9222"),
        ("http://10.0.0.2", "http://10.0.0.2"),
        ("http://172.16.0.2:1", "http://172.16.0.2:1"),
        ("http://100.101.102.103:65535", "http://100.101.102.103:65535"),
        ("https://workstation.tail123.ts.net/remote/cdp", "https://workstation.tail123.ts.net/remote/cdp"),
        ("http://workstation", "http://workstation"),
        ("http://xn--bcher-kva.example", "http://xn--bcher-kva.example"),
        ("http://example.com./", "http://example.com."),
        ("http://[::1]:9222/", "http://[::1]:9222"),
        ("http://[FD7A:115C:A1E0::1]:9222", "http://[fd7a:115c:a1e0::1]:9222"),
        ("http://[::ffff:192.0.2.1]/base", "http://[::ffff:192.0.2.1]/base"),
        ("http://localhost/a-b/c_d/ef.gh/~cdp", "http://localhost/a-b/c_d/ef.gh/~cdp"),
    ],
)
def test_validate_canonical_base(url, expected):
    assert validate_cdp_url(url) == expected
    assert validate_cdp_url(expected) == expected


INVALID_URLS = [
    None, 123, b"http://localhost:9222", "", "localhost:9222", "//localhost:9222",
    "http:localhost:9222", "http:/localhost:9222", "http:///localhost:9222",
    "http://", "https://:9222", "file:///tmp/version", "ftp://localhost",
    "ws://localhost:9222", "wss://localhost:9222", "javascript:alert(1)",
    " http://localhost", "http://localhost ", "http://local host",
    "http://localhost\n", "http://local\thost", "http://localhost/\r\nX-Token:value",
    "\x00http://localhost", "http://localhost/\x7f", "http://localhost/\u00a0",
    "http://user@localhost", "http://user:password@localhost", "http://@localhost",
    "http://user%40localhost@other", "http://localhost?", "http://localhost?q=secret",
    "http://localhost#", "http://localhost#fragment", "http://localhost/base?x=y",
    "http://localhost\\@other", "http://localhost/base\\other", "http://local%68ost",
    "http://localhost:", "http://localhost:0", "http://localhost:65536",
    "http://localhost:-1", "http://localhost:+80", "http://localhost:abc",
    "http://localhost:80:90", "http://localhost:１２３", "http://[::1]:",
    "http://::1:9222", "http://[::1", "http://[::1]junk", "http://[invalid]",
    "http://[127.0.0.1]", "http://[v1.fe80]", "http://[fe80::1%25eth0]",
    "http://-bad.example", "http://bad-.example", "http://a..b", "http://.example",
    "http://example..", "http://under_score.example", "http://*.example",
    "http://bücher.example", "http://example。com", "http://example.com：80",
    "http://" + "a" * 64 + ".example", "http://" + ".".join(["a" * 63] * 4),
    "http://127.1", "http://2130706433", "http://0177.0.0.1", "http://0x7f000001",
    "http://0x7f.0.0.1", "http://127.0.0.999", "http://1.2.3.04",
    "http://localhost//", "http://localhost/base//next", "http://localhost/./base",
    "http://localhost/base/../next", "http://localhost/..", "http://localhost/.",
    "http://localhost/%2e%2e", "http://localhost/%2Fother", "http://localhost/%252f",
    "http://localhost/path%20name", "http://localhost/%", "http://localhost/base;token=x",
    "http://localhost/base:other", "http://localhost/base@other", "http://localhost/[base]",
    "http://localhost/" + "x" * 4096,
]


@pytest.mark.parametrize("url", INVALID_URLS)
def test_validate_rejects_malformed_or_ambiguous_urls(url):
    with pytest.raises(ValueError, match="^Invalid CDP endpoint URL\\.$"):
        validate_cdp_url(url)
    assert_failure(probe_cdp(url), "Invalid CDP endpoint URL.")


def test_invalid_url_does_not_reach_server(http_server):
    server = http_server()
    assert_failure(probe_cdp(server.url + f"/?{SECRET}"))
    assert server.requests == []


@pytest.mark.parametrize("base_path", ["", "/", "/remote/cdp", "/remote/cdp/"])
def test_probe_uses_only_version_under_literal_base_path(http_server, base_path):
    server = http_server()
    result = probe_cdp(server.url + base_path)
    assert result == {
        "connected": True,
        "browser": VERSION["Browser"],
        "protocol_version": "1.3",
        "error": None,
    }
    assert len(server.requests) == 1
    assert server.requests[0]["method"] == "GET"
    assert server.requests[0]["path"] == base_path.rstrip("/") + "/json/version"
    headers = {k.lower(): v for k, v in server.requests[0]["headers"].items()}
    assert headers["accept"] == "application/json"
    assert not ({"cookie", "authorization", "proxy-authorization"} & headers.keys())


def test_response_whitelist_and_no_cookie_persistence(http_server):
    payload = {
        **VERSION,
        "webSocketDebuggerUrl": f"ws://localhost/devtools/browser/{SECRET}",
        "User-Agent": SECRET,
        "cookies": [{"value": SECRET}],
        "tabs": [{"title": SECRET, "url": f"https://{SECRET}.example"}],
        "error": SECRET,
    }
    server = http_server(
        body=json.dumps(payload).encode(), headers={"Set-Cookie": f"session={SECRET}"}
    )
    for _ in range(2):
        result = probe_cdp(server.url)
        assert set(result) == RESULT_KEYS
        assert result["connected"] is True
        assert result["browser"] == VERSION["Browser"]
        assert SECRET not in json.dumps(result)
        assert "webSocketDebuggerUrl" not in json.dumps(result)
    assert len(server.requests) == 2
    assert all("cookie" not in {k.lower() for k in req["headers"]} for req in server.requests)


@pytest.mark.parametrize("status", [300, 301, 302, 303, 304, 305, 306, 307, 308])
def test_redirects_are_not_followed(http_server, status):
    destination = http_server()
    source = http_server(
        status=status, body=SECRET.encode(),
        headers={"Location": destination.url + f"/{SECRET}"},
    )
    assert_failure(probe_cdp(source.url), "CDP endpoint redirected; redirects are not allowed.")
    assert len(source.requests) == 1
    assert destination.requests == []


@pytest.mark.parametrize("location", ["/json/version", "//127.0.0.1:1/secret", "file:///tmp/secret", "data:text/plain,secret", "ftp://localhost/secret"])
def test_relative_and_non_http_redirects_are_not_followed(http_server, location):
    server = http_server(status=302, headers={"Location": location}, body=SECRET.encode())
    assert_failure(probe_cdp(server.url))
    assert len(server.requests) == 1


def test_all_environment_proxies_are_bypassed(http_server, monkeypatch):
    target = http_server()
    proxy = http_server(status=502, body=SECRET.encode())
    for variable in ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        monkeypatch.setenv(variable, proxy.url)
    for variable in ("no_proxy", "NO_PROXY"):
        monkeypatch.setenv(variable, "")
    # Ignore CGI's special uppercase HTTP_PROXY behavior: test both casings directly.
    monkeypatch.delenv("REQUEST_METHOD", raising=False)
    assert probe_cdp(target.url)["connected"] is True
    assert len(target.requests) == 1
    assert proxy.requests == []


def test_https_environment_proxies_are_also_bypassed(http_server, monkeypatch):
    proxy = http_server(status=502)
    for variable in ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        monkeypatch.setenv(variable, proxy.url)
    for variable in ("no_proxy", "NO_PROXY"):
        monkeypatch.setenv(variable, "")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reserved:
        reserved.bind(("127.0.0.1", 0))
        url = f"https://127.0.0.1:{reserved.getsockname()[1]}"
        # A direct connection is refused; a proxy path would emit CONNECT to
        # the real HTTP server above instead. No remote TLS host is accessed.
        assert_failure(probe_cdp(url, timeout=0.2), "Unable to connect to CDP endpoint.")
    assert proxy.requests == []


def test_installed_global_opener_is_not_used(http_server, monkeypatch):
    import urllib.request

    target = http_server()
    proxy = http_server(status=502)
    for variable in ("no_proxy", "NO_PROXY"):
        monkeypatch.setenv(variable, "")
    # This is a real stdlib HTTP opener, not a mocked HTTP transport.
    global_opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy.url}))
    monkeypatch.setattr(urllib.request, "_opener", global_opener)
    assert probe_cdp(target.url)["connected"] is True
    assert len(target.requests) == 1
    assert proxy.requests == []


@pytest.mark.parametrize("status", [201, 204, 400, 401, 403, 404, 429, 500, 503])
def test_http_errors_have_fixed_safe_output(http_server, status):
    server = http_server(status=status, body=SECRET.encode(), headers={"X-Secret": SECRET})
    result = probe_cdp(server.url)
    assert_failure(result, "CDP endpoint returned an HTTP error.")
    assert server.url not in result["error"]


@pytest.mark.parametrize("content_length", [True, False])
def test_oversized_body_rejected_with_or_without_length(http_server, content_length):
    server = http_server(body=b" " * (BODY_LIMIT + 1), content_length=content_length)
    assert_failure(probe_cdp(server.url), "CDP response is too large.")


def test_oversized_declared_length_rejected_before_waiting_for_body(http_server):
    server = http_server(headers={"Content-Length": str(BODY_LIMIT + 1)}, body_delay=0.2)
    assert_failure(probe_cdp(server.url, timeout=0.05), "CDP response is too large.")


def test_body_at_limit_is_accepted(http_server):
    payload = json.dumps(VERSION).encode()
    server = http_server(body=payload + b" " * (BODY_LIMIT - len(payload)))
    assert probe_cdp(server.url)["connected"] is True


def test_chunked_body_is_also_bounded(http_server):
    def respond(handler):
        payload = b" " * (BODY_LIMIT + 1)
        handler.send_response(200)
        handler.send_header("Transfer-Encoding", "chunked")
        handler.send_header("Connection", "close")
        handler.end_headers()
        handler.wfile.write(f"{len(payload):x}\r\n".encode() + payload + b"\r\n0\r\n\r\n")
        handler.close_connection = True

    server = http_server(responder=respond)
    assert_failure(probe_cdp(server.url), "CDP response is too large.")


@pytest.mark.parametrize(
    "body",
    [
        b"", b"not json", b"<html>error</html>", b"\xff", b"null", b"[]", b"true", b"1",
        b"{}", b'{"Browser": "Chrome/123"}', b'{"Protocol-Version": "1.3"}',
        b'{"Browser": "Chrome/123", "Protocol-Version": "1.3", "extra": NaN}',
        b'{"Browser": "Chrome/123", "Protocol-Version": "1.3", "extra": Infinity}',
        b'{"Browser": "Chrome/123", "Browser": "Chrome/456", "Protocol-Version": "1.3"}',
        b"[" * 2000 + b"0" + b"]" * 2000,
        b"9" * 5000,
        json.dumps({**VERSION, "Browser": None}).encode(),
        json.dumps({**VERSION, "Browser": 123}).encode(),
        json.dumps({**VERSION, "Browser": {"cookie": SECRET}}).encode(),
        json.dumps({**VERSION, "Browser": ""}).encode(),
        json.dumps({**VERSION, "Browser": "Chrome/123\n" + SECRET}).encode(),
        json.dumps({**VERSION, "Browser": "Chrome/" + "1" * 1000}).encode(),
        json.dumps({**VERSION, "Browser": f"ws://localhost/{SECRET}"}).encode(),
        json.dumps({**VERSION, "Browser": f"session={SECRET}"}).encode(),
        json.dumps({**VERSION, "Protocol-Version": False}).encode(),
        json.dumps({**VERSION, "Protocol-Version": ["1.3"]}).encode(),
        json.dumps({**VERSION, "Protocol-Version": ""}).encode(),
        json.dumps({**VERSION, "Protocol-Version": SECRET}).encode(),
    ],
)
def test_invalid_json_and_metadata_fail_safely(http_server, body):
    server = http_server(body=body)
    assert_failure(probe_cdp(server.url), "Invalid CDP version response.")


@pytest.mark.parametrize("browser", ["Chrome/123.0", "HeadlessChrome/123.0.1", "Microsoft Edge/123.0", "Firefox/143.0a1"])
def test_common_browser_product_versions(http_server, browser):
    server = http_server(body=json.dumps({**VERSION, "Browser": browser}).encode())
    assert probe_cdp(server.url)["browser"] == browser


def test_compressed_payload_is_not_expanded(http_server):
    server = http_server(headers={"Content-Encoding": "gzip"})
    assert_failure(probe_cdp(server.url), "Invalid CDP version response.")


@pytest.mark.parametrize("length", ["-1", "not-a-number", "1, 2"])
def test_invalid_content_length_is_safe(http_server, length):
    server = http_server(headers={"Content-Length": length})
    assert_failure(probe_cdp(server.url), "Invalid CDP version response.")


def test_truncated_body_is_safe(http_server):
    server = http_server(headers={"Content-Length": "1000"})
    assert_failure(probe_cdp(server.url), "Invalid CDP version response.")


@pytest.mark.parametrize("delay", ["header_delay", "body_delay"])
def test_network_timeout_has_safe_output(http_server, delay):
    server = http_server(**{delay: 0.2})
    assert_failure(probe_cdp(server.url, timeout=0.03), "CDP probe timed out.")


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), -float("inf"), None, "3", True, 10**1000])
def test_invalid_timeout_does_not_make_request(http_server, timeout):
    server = http_server()
    assert_failure(probe_cdp(server.url, timeout=timeout), "Invalid CDP probe timeout.")
    assert server.requests == []


def test_connection_refused_is_safe():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reserved:
        # Bind without listening so no other process can take this loopback port.
        reserved.bind(("127.0.0.1", 0))
        url = f"http://127.0.0.1:{reserved.getsockname()[1]}"
        result = probe_cdp(url, timeout=0.2)
    assert_failure(result, "Unable to connect to CDP endpoint.")
    assert url not in result["error"]
