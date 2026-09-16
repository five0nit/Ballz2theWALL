"""Real headless-browser info-page gate. Run with `uv run --with playwright`."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from playwright.sync_api import sync_playwright


def check_typography(browser, url, out):
    """Check text ranges, not only boxes, across system-font fallbacks."""
    rows = []
    widths = [320, 360, 390, 412, 620, 621, 768, 800, 801, 1024, 1100, 1440]
    fonts = {'native': None, 'sans': 'sans-serif', 'wide': '"DejaVu Sans", sans-serif'}
    for label, font in fonts.items():
        context = browser.new_context(viewport={'width': 390, 'height': 844},
                                      is_mobile=True, has_touch=True,
                                      java_script_enabled=False)
        page = context.new_page()
        response = page.goto(url, wait_until='networkidle')
        assert response and response.status == 200
        if font:
            # Changing user agent does not change installed fonts on the QA host.
            page.evaluate('(font) => document.documentElement.style.setProperty("--heading", font)', font)
        for width in widths:
            page.set_viewport_size({'width': width, 'height': 844})
            geometry = page.evaluate('''() => {
                const headings = [...document.querySelectorAll('h1, h2')].map(e => {
                    const box = e.getBoundingClientRect();
                    const walker = document.createTreeWalker(e, NodeFilter.SHOW_TEXT);
                    const rects = [];
                    let node;
                    while ((node = walker.nextNode())) {
                        if (!node.textContent.trim()) continue;
                        const range = document.createRange();
                        range.selectNodeContents(node);
                        for (const r of range.getClientRects()) {
                            rects.push({left:r.left, right:r.right, top:r.top});
                        }
                    }
                    return {text:e.textContent, font:getComputedStyle(e).fontFamily,
                            size:getComputedStyle(e).fontSize, rects,
                            left:box.left, right:box.right,
                            clipped:rects.some(r => r.left < box.left - 1 || r.right > box.right + 1)};
                });
                return {width:innerWidth, scroll:document.documentElement.scrollWidth,
                        heroLines:new Set(headings[0].rects.map(r => r.top)).size, headings};
            }''')
            passed = (geometry['width'] == width and geometry['scroll'] <= width
                      and geometry['heroLines'] == 3
                      and not any(h['clipped'] for h in geometry['headings']))
            rows.append({'font': label, 'width': width, 'passed': passed, **geometry})
            if width in (390, 1440):
                page.screenshot(path=str(out / f'typography-{label}-{width}.png'))
        context.close()
    receipt = {'url': url, 'cases': rows, 'passed': sum(r['passed'] for r in rows)}
    (out / 'typography.json').write_text(json.dumps(receipt, indent=2) + '\n')
    failures = [{'font': r['font'], 'width': r['width'], 'scroll': r['scroll'],
                 'heroLines': r['heroLines'],
                 'clipped': [h['text'] for h in r['headings'] if h['clipped']]}
                for r in rows if not r['passed']]
    assert not failures, failures
    return {'passed': receipt['passed'], 'total': len(rows)}


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
                                          java_script_enabled=scripting, has_touch=width <= 390)
            page = context.new_page()
            errors = []
            failed_requests = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
            page.on('requestfailed', lambda request: failed_requests.append(request.url))
            response = page.goto(args.url, wait_until='networkidle', timeout=30000)
            assert response and response.status == 200
            assert page.title().startswith('Ballz2theWALL')
            assert page.locator('h1').count() == 1
            assert '0.3.0a0.dev6' in page.locator('.release-note').inner_text()
            assert 'v0.2.0a2' in page.locator('.release-note').inner_text()
            assert 'acceptance pending' in page.locator('.release-note').inner_text()
            assert page.locator('.feature-row').count() == 5
            assert 'not in the v0.2.0a2 downloads' in page.locator('#features').inner_text()
            downloads = page.locator('.button-download').evaluate_all('(els)=>els.map(e=>e.href)')
            assert len(downloads) == 2
            assert all('/releases/download/v0.2.0a2/' in url for url in downloads)
            missing_anchors = page.locator('a[href^="#"]').evaluate_all(
                '(els)=>els.map(e=>e.getAttribute("href")).filter(h=>!document.getElementById(h.slice(1)))')
            assert not missing_anchors, missing_anchors
            geometry = page.evaluate('({width:innerWidth,scroll:document.documentElement.scrollWidth})')
            assert geometry['width'] == width and geometry['scroll'] <= width, (width, geometry)
            name = f'{width}-reduce{int(reduced)}-js{int(scripting)}'
            page.screenshot(path=str(args.out / f'{name}.png'), full_page=True)
            page.screenshot(path=str(args.out / f'{name}-hero.png'))
            page.locator('#features').scroll_into_view_if_needed()
            # Viewport capture avoids fixed-overlay artifacts from element crops.
            page.screenshot(path=str(args.out / f'{name}-features.png'))
            if scripting:
                switch = page.locator('#preview-switch')
                switch.tap() if width <= 390 else switch.click()
                assert switch.get_attribute('aria-pressed') == 'true'
                assert page.locator('#preview-state').inner_text() == 'ON'
                switch.press('Space')
                assert switch.get_attribute('aria-pressed') == 'false'
                for summary in page.locator('summary').all():
                    summary.click()
                    assert summary.evaluate('(e)=>e.parentElement.open')
                page.locator('.hero-actions a').first.click()
                assert page.url.endswith('#features')
                page.locator('.hero-actions a').nth(1).click()
                assert page.url.endswith('#download')
                page.screenshot(path=str(args.out / f'{name}-download.png'))
            else:
                assert page.locator('#preview-switch').is_disabled()
                assert page.locator('.button-download').count() == 2
            assert not errors, errors
            assert not failed_requests, failed_requests
            rows.append({'name':name, 'geometry':geometry, 'console_errors':errors,
                         'failed_requests':failed_requests, 'downloads':downloads,
                         'source_version':'0.3.0a0.dev6', 'download_version':'v0.2.0a2',
                         'preview': 'on/off+keyboard' if scripting else 'disabled fallback',
                         'screenshot':f'{name}.png'})
            context.close()
        typography = check_typography(browser, args.url, args.out)
        browser.close()
    receipt = {'url':args.url,'cases':rows,'passed':len(rows),'typography':typography}
    (args.out / 'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))


if __name__ == '__main__':
    main()
