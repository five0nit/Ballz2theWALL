# Verification — 0.2.0a1 guided-setup local alpha

Current machine evidence is in `verification/0.2.0a1/`; artifact binding is in
`dist/RELEASE-0.2.0a1.json`. Historical runtime-parser and browser evidence remains
in [0.1.1 verification](VERIFICATION-0.1.1.md), not relabeled as a Mac test.

Verified scope: source suite; immutable wheel; native Windows x64 private install,
installed version/import provenance, owner-only transactions, cross-process
locking, junction/hardlink rejection, ON/OFF original-byte restoration and dialog
rendering. Test profiles and state are synthetic temporary directories only.
Native GUI render is offscreen: it proves rendered controls, not user clicks.

Native macOS prompt/Settings/Terminal-responsibility acceptance, Windows ARM64,
code signing/notarization and live authenticated model calls remain **unverified**.
No real agent configuration, authentication, OS grant, gateway, public release or
existing Start Menu shortcut was changed for verification.

`pytest` skips platform-exclusive cases on the wrong host; record them separately.
The native Windows gate uses the actual installed wheel, not source imports.
Final exact counts and command results are recorded in `verification/0.2.0a1/gates.json`.

- Source: **450 passed, 3 skipped**.
- Fresh Python 3.11 wheel: **450 passed, 3 skipped**, outside the source tree.
- Native Windows installed-wheel subset: **26 passed, 2 skipped**.
- Native Windows Store: **8 check groups passed**.
- Native shortcut: actual COM creation/readback passed with only Programs redirected to scratch.
- Installed `ballz` console: version, ON, status, OFF, and exact original-byte restoration passed.
- Ruff and Mac shell syntax checks passed. Staged whitespace checks passed with
  `core.whitespace=blank-at-eol,space-before-tab,cr-at-eol,-blank-at-eof`; raw Windows
  CRLF and terminal log blank lines are retained verbatim.

Preflight: see `discovery/GUIDED-INSTALL.md`. Automated discovery was inconclusive;
manual inspection retained the canonical MIT controller, selected uv as bootstrap
utility and native dialogs/APIs for onboarding. Cua companion integration remains
outside this increment; no universal desktop-control claim follows from setup.
