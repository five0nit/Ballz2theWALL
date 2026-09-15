#!/bin/bash
# Double-click from Finder. Terminal is the stable macOS permission owner.
set -euo pipefail
if [ "$(uname -s)" != Darwin ]; then
    printf '%s\n' 'This installer runs on a Mac. Use Install-Windows.cmd on Windows.' >&2
    exit 2
fi
HERE="$(cd "$(dirname "$0")" && pwd)"
MAC_VERSION="$(/usr/bin/sw_vers -productVersion)"
if [ "${MAC_VERSION%%.*}" -lt 11 ]; then
    /usr/bin/osascript -e 'display dialog "Ballz2theWALL setup needs macOS 11 or newer. This Mac was not changed." with title "Ballz2theWALL" buttons {"OK"} default button "OK"'
    exit 2
fi
case "$(uname -m)" in
    arm64) ARCH=aarch64; SHA=5bb0e5fe008a773c3dbcb97ff79cd89e1241464fe9d2f986d52ad8f1b037bd62 ;;
    x86_64) ARCH=x86_64; SHA=b3b2137477cf96c9686ebfb71524614cec780c673fd73e59bce099aef02e70e8 ;;
    *) printf '%s\n' 'Unsupported Mac processor.' >&2; exit 2 ;;
esac
# Reject incomplete bundles before creating state or downloading a runtime.
if [ -e "$HERE/payload" ]; then
    shopt -s nullglob
    WHEELS=("$HERE"/payload/*.whl)
    if [ "${#WHEELS[@]}" -ne 1 ] || [ ! -f "$HERE/payload/SHA256SUMS.json" ]; then
        printf '%s\n' 'Incomplete package. Extract the entire installer ZIP before starting.' >&2
        exit 2
    fi
elif [ ! -f "$HERE/../pyproject.toml" ]; then
    printf '%s\n' 'Missing package. Extract the entire installer ZIP before starting.' >&2
    exit 2
fi
if [ "${BALLZ_NONINTERACTIVE:-0}" != 1 ]; then
    /usr/bin/osascript -e 'display dialog "Install Ballz2theWALL for this Mac account? Setup downloads its private runtime, then guides you through Mac access approvals. No Python or Homebrew setup needed. Your agent remains OFF until you choose ON." with title "Install Ballz2theWALL" buttons {"Cancel", "Install"} default button "Install" cancel button "Cancel"' >/dev/null || exit 0
fi
ROOT="${BALLZ_INSTALL_ROOT:-$HOME/Library/Application Support/Ballz2theWALL}"
umask 077
mkdir -p "$ROOT"
LOG="$ROOT/install.log"
failed() {
    code=$?
    if [ "$code" -ne 0 ]; then
        /usr/bin/osascript -e 'on run argv' \
          -e 'display dialog "Installation did not finish. Check your internet connection, then open Install-Mac.command again. Details: " & item 1 of argv with title "Ballz2theWALL" buttons {"OK"} default button "OK"' \
          -e 'end run' "$LOG" || true
    fi
}
trap failed EXIT
printf '%s\n' 'Installing Ballz2theWALL. Keep this window open; setup appears when ready.'
mkdir -p "$ROOT/bootstrap"
ARCHIVE="$ROOT/bootstrap/uv-$ARCH-0.12.5.tar.gz"
if [ ! -f "$ARCHIVE" ] || [ "$(/usr/bin/shasum -a 256 "$ARCHIVE" | /usr/bin/cut -d ' ' -f 1)" != "$SHA" ]; then
    /usr/bin/curl --fail --location --proto '=https' --tlsv1.2 --connect-timeout 30 --max-time 600 \
      "https://github.com/astral-sh/uv/releases/download/0.12.5/uv-$ARCH-apple-darwin.tar.gz" -o "$ARCHIVE.download" >> "$LOG" 2>&1
    ACTUAL="$(/usr/bin/shasum -a 256 "$ARCHIVE.download" | /usr/bin/cut -d ' ' -f 1)"
    if [ "$ACTUAL" != "$SHA" ]; then printf '%s\n' 'Runtime download checksum mismatch.' >> "$LOG"; exit 2; fi
    mv "$ARCHIVE.download" "$ARCHIVE"
fi
/usr/bin/tar -xzf "$ARCHIVE" -C "$ROOT/bootstrap" >> "$LOG" 2>&1
UV="$ROOT/bootstrap/uv-$ARCH-apple-darwin/uv"
export UV_PYTHON_INSTALL_DIR="$ROOT/python"
export UV_CACHE_DIR="$ROOT/cache"
unset UV_PYTHON_PREFERENCE
export UV_PYTHON_DOWNLOADS=automatic
export UV_NO_CONFIG=1
if [ ! -x "$ROOT/runtime/bin/python" ]; then
    "$UV" venv --no-config --managed-python --python 3.11 "$ROOT/runtime" >> "$LOG" 2>&1
fi
PYTHON="$ROOT/runtime/bin/python"
if [ -d "$HERE/payload" ]; then
    TARGET="$("$PYTHON" -I - "$HERE/payload" <<'PY'
import hashlib, json, pathlib, sys
root = pathlib.Path(sys.argv[1])
manifest = json.loads((root / 'SHA256SUMS.json').read_text())
wheels = list(root.glob('ballz2thewall-*.whl'))
if len(wheels) != 1:
    raise SystemExit('Expected exactly one Ballz2theWALL wheel.')
wheel = wheels[0]
if manifest.get(wheel.name) != hashlib.sha256(wheel.read_bytes()).hexdigest():
    raise SystemExit('Package checksum mismatch. Download the complete installer again.')
print(wheel)
PY
)"
elif [ -f "$HERE/../pyproject.toml" ]; then
    TARGET="$(cd "$HERE/.." && pwd)"
else
    printf '%s\n' 'Missing package. Extract the entire installer ZIP before starting.' >> "$LOG"
    exit 2
fi
"$UV" pip install --no-config --python "$PYTHON" --reinstall-package ballz2thewall "$TARGET" >> "$LOG" 2>&1
"$PYTHON" -I -m ballz2thewall --version >> "$LOG" 2>&1
mkdir -p "$HOME/Applications"
LAUNCHER="$HOME/Applications/Ballz2theWALL.command"
"$PYTHON" -I - "$PYTHON" "$LAUNCHER" <<'PY'
import os, pathlib, shlex, sys
python, target = sys.argv[1:]
path = pathlib.Path(target)
if path.is_symlink():
    raise SystemExit('Existing launcher is a symlink. Choose a regular launcher path.')
content = '#!/bin/bash\ncd "$HOME"\nexec ' + shlex.quote(python) + ' -I -m ballz2thewall setup --gui\n'
path.write_text(content)
os.chmod(path, 0o700)
PY
printf 'Installed. Open %s any time to finish setup or turn ON/OFF.\n' "$LAUNCHER"
trap - EXIT
if [ "${BALLZ_NO_LAUNCH:-0}" != 1 ]; then
    exec "$PYTHON" -I -m ballz2thewall setup --gui
fi
