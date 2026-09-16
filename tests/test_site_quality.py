"""Regression checks for issues reproduced by the live Lighthouse audit."""
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

SITE = Path(__file__).resolve().parents[1] / "site"


class SiteElements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = []

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


def css_rule(selector):
    css = (SITE / "style.css").read_text()
    match = re.search(re.escape(selector) + r"\s*\{([^}]+)\}", css)
    assert match, selector
    return match.group(1)


def css_color(selector, property_name):
    match = re.search(re.escape(property_name) + r":\s*(#[0-9a-f]{6})", css_rule(selector))
    assert match, (selector, property_name)
    return match.group(1)


def luminance(color):
    channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return sum(c * weight for c, weight in zip(linear, (0.2126, 0.7152, 0.0722)))


def contrast(foreground, background):
    light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def test_small_accent_text_has_aa_contrast():
    accent = css_color(":root", "--accent")
    paper = css_color(":root", "--paper")
    assert contrast(accent, paper) >= 4.5


def test_plate_serial_has_aa_contrast():
    foreground = css_color(".plate-serial", "color")
    background = css_color(".switch-plate", "background")
    assert contrast(foreground, background) >= 4.5


def test_switch_accessible_name_contains_visible_label():
    document = SiteElements()
    document.feed((SITE / "index.html").read_text())
    switches = [attrs for tag, attrs in document.elements if attrs.get("id") == "preview-switch"]
    assert len(switches) == 1
    assert "on off" in switches[0]["aria-label"].lower()
    assert switches[0]["aria-pressed"] == "false"


@pytest.mark.parametrize("runtime", ["Hermes", "OpenAI Codex", "Claude Code", "OpenClaw"])
def test_adapter_accessible_name_contains_visible_label(runtime):
    document = SiteElements()
    document.feed((SITE / "index.html").read_text())
    links = [attrs for tag, attrs in document.elements
             if tag == "a" and "runtime-link" in attrs.get("class", "").split()
             and runtime in attrs.get("aria-label", "")]
    assert len(links) == 1
    assert links[0]["aria-label"].startswith("Adapter notes")
