"""Real headless-browser info-page gate. Run with `uv run --with playwright`."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--browser', default=shutil.which('chromium'))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    rows = []
    with sync_playwright() as play:
        browser = play.chromium.launch(headless=True, executable_path=args.browser,
                                       args=['--no-sandbox', '--disable-dev-shm-usage'])
        for width, height, reduced, scripting in [(1440,1000,False,True), (390,844,False,True),
                                                 (320,720,True,True), (390,844,True,False)]:
            context = browser.new_context(viewport={'width':width, 'height':height},
                                          reduced_motion='reduce' if reduced else 'no-preference',
                                          java_script_enabled=scripting)
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
            response = page.goto(args.url, wait_until='networkidle', timeout=30000)
            assert response and response.status == 200
            assert page.title().startswith('Ballz2theWALL')
            assert page.locator('h1').count() == 1
            geometry = page.evaluate('({width:innerWidth,scroll:document.documentElement.scrollWidth})')
            assert geometry['width'] == width and geometry['scroll'] <= width, (width, geometry)
            name = f'{width}-reduce{int(reduced)}-js{int(scripting)}'
            page.screenshot(path=str(args.out / f'{name}.png'), full_page=True)
            if scripting:
                switch = page.locator('#preview-switch')
                switch.click()
                assert switch.get_attribute('aria-pressed') == 'true'
                assert page.locator('#preview-state').inner_text() == 'ON'
                switch.press('Space')
                assert switch.get_attribute('aria-pressed') == 'false'
                for summary in page.locator('summary').all():
                    summary.click()
                    assert summary.evaluate('(e)=>e.parentElement.open')
                page.locator('.hero-actions a').first.click()
                assert page.url.endswith('#download')
                page.screenshot(path=str(args.out / f'{name}-download.png'))
            else:
                assert page.locator('#preview-switch').is_disabled()
                assert page.locator('.button-download').count() == 2
            assert not errors, errors
            rows.append({'name':name, 'geometry':geometry, 'console_errors':errors,
                         'preview': 'on/off+keyboard' if scripting else 'disabled fallback',
                         'screenshot':f'{name}.png'})
            context.close()
        browser.close()
    receipt = {'url':args.url,'cases':rows,'passed':len(rows)}
    (args.out / 'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))


if __name__ == '__main__':
    main()
