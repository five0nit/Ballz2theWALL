# OpenClaw + public info page preflight

Target: extend the canonical MIT Python controller with reversible local OpenClaw support, retain Hermes/Codex/Claude, and publish a dependency-free mobile product info page after audit.

## Discovery receipts

- `/tmp/brief2ship-preflight-ballz-openclaw-lIXOvS/discovery.json`: broad search partial/inconclusive, no candidates; npm HTTP 400.
- `/tmp/brief2ship-preflight-openclaw-focused-Gg0GRF/discovery.json`: focused search partial/inconclusive. Repository size and npm response bounds prevented complete upstream inspection. No candidate code executed.
- `/tmp/brief2ship-preflight-ballz-site-dglosX/discovery.json`: static site search inconclusive. Supplemented by direct GitHub source inspection below.

CLI no-selection outcomes retained, not reinterpreted as automatic approval. Manual scoped decisions follow from actual source inspection.

## Runtime decision: selective-reuse

Keep canonical Ballz2theWALL at baseline `b323810`. Inspected `adapters.py`, `config.py`, `doctor.py`, `cli.py`, `onboarding.py`, manifest and MIT license. Reuse its native adapter, exact-byte transaction and guided setup architecture. Scope fit 5/5; implementation reuse 5/5; dependency cost 5/5; native OpenClaw evidence 2/5 pending source/CLI validation.

OpenClaw is an existing external runtime, not a new bundled dependency. Installed package `/home/fiv30nit/.npm-global/lib/node_modules/openclaw`, version `2026.6.1`, CLI revision `2e08f0f`; installed LICENSE is MIT with third-party notices. Inspect installed native semantics and verify scratch-only parser/approval behavior before enabling support. No live profiles, auth stores, model sessions or background gateways used for testing. Latest public npm metadata (`2026.9.4`) does not prove compatibility with the installed version.

Reject `@openclaw/ai` as a controller base: provider/streaming library, not the native execution policy controller. Reject open-im-server (chat server) and awesome-openclaw-skills (catalog), neither implements this adapter contract.

## Info page decision: build-clean within canonical repo

Inspected `xu42/simple-app-landing-page-template` at `0d16a506336666c71f9d25dd6f2e99c3db80b23f` via GitHub README, root contents and `index.html`. Pure HTML and CSS are appropriate (architecture fit 5/5); app-store badges, translation-app copy and carousel are poor product fit (1/5). Script calls `addEventListener` on absent `.carousel-button.prev/next` elements. Reject template reuse; retain only the general dependency-free static approach. No source copied.

Inspected discovery's source/manifest/license evidence for `Mohcka/Website-Editor-Tool-via-Static-Website-Generator-w-CMS-` at `b9295660e5c69d5971789656bd13b8fd0cff53a5`: Gatsby/Netlify CMS, 52 declared dependencies, unrelated editing/admin surface. Architecture fit 1/5, product fit 1/5, dependency cost 1/5. Reject. `osc-vitap/test-site-hugo` remains uninspected, not selected.

Design directions considered: industrial switch plate; editorial installation manual; conventional app-store page. Select **industrial switch plate**: warm paper, ink typography, restrained safety-orange action, physical ON/OFF object clearly labeled as a website demonstration. Audience: owners of existing supported agents. Two-second job: download, install, approve required settings, choose agent, turn ON. One dominant headline and real release/download/docs links. Mobile controls stack; no carousel, artificial metrics, fake testimonials or desktop-control promises. Build standalone HTML/CSS/minimal JS in `site/`, no frontend dependencies.

## JSON5 parser dependency: use-as-library

Receipt `/tmp/brief2ship-preflight-ballz-json5-VnM3o3/discovery.json` remained inconclusive. Supplementary direct PyPI metadata and pinned upstream `dpranke/pyjson5` at `b1b09eb8eea3738f619b955d00ac6ec4a940a007` inspected: `json5/lib.py` implements `loads`, `allow_duplicate_keys=False`, and custom `parse_constant`. Apache-2.0 code, Python >=3.8, pure Python. Select `json5==0.15.0` as runtime library for OpenClaw JSON5 syntax only; never loosen strict controller receipts or other adapters. Fit 5/5, compatibility 5/5, dependency weight 4/5. Comments normalize while ON; exact original bytes restore on OFF. No candidate tests executed during discovery.

## Release gates

Adapter native-source audit, tests including failure/recovery and scope isolation, clean installed wheel round-trip, existing adapters regression, installer archive/hash verification, publication content/secret audit, desktop + 390px visual QA, reduced-motion and no-JS usability. Publish explicitly as unsigned alpha; physical Mac permission/Terminal attribution acceptance remains unverified and not a passed gate. No claim of universal desktop access or provider-policy changes.
