import pytest

from ballz2thewall import onboarding as ob


@pytest.mark.parametrize("version,expected", [("10.15.7", False), ("11.0", True), ("26.0", True), ("", False)])
def test_mac_api_version_gate(monkeypatch, version, expected):
    monkeypatch.setattr(ob.platform, "mac_ver", lambda: (version, (), ""))
    assert ob.mac_supported() is expected


def test_catalina_does_not_load_crash_prone_apis(monkeypatch):
    monkeypatch.setattr(ob.platform, "mac_ver", lambda: ("10.15.7", (), ""))
    monkeypatch.setattr(ob.ctypes, "CDLL", lambda _: pytest.fail("framework called"))
    assert ob.mac_permissions()["responsible_app"] == "unsupported_os"
    monkeypatch.setattr(ob.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(ob, "terminal_responsible", lambda: True)
    with pytest.raises(ValueError, match="11"):
        ob.request_mac("screen_recording")
