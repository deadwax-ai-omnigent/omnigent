#!/bin/bash
# Deadwax deploy: build the rebranded web bundle and serve it from the active
# omnigent install on this Mac, then restart the host service.
#
# Our Deadwax customizations are frontend-only (the static web-ui bundle), so we
# build it here and copy it over whatever omnigent the runtime uses — functionally
# identical to running the fork, with none of the dependency-reinstall risk. Run
# this after each upstream sync (or any web UI change).
set -euo pipefail
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"

FORK_DIR="$(cd "$(dirname "$0")/.." && pwd)"
echo "==> Building rebranded web UI ($FORK_DIR/web)"
cd "$FORK_DIR/web"
[ -d node_modules ] || pnpm install --frozen-lockfile
pnpm run build   # vite outputs to ../omnigent/server/static/web-ui

FORK_UI="$FORK_DIR/omnigent/server/static/web-ui"
# Resolve the active install's web-ui. omnigent runs under uv's python (3.12),
# not the system python3 — so locate the uv-tool install directly rather than
# `python3 -c 'import omnigent'` (which fails: ModuleNotFoundError under 3.9).
PKG_UI="$(ls -d "$HOME"/.local/share/uv/tools/omnigent/lib/python*/site-packages/omnigent/server/static/web-ui 2>/dev/null | head -1)"
if [ -z "$PKG_UI" ]; then
  PKG_UI="$(uv tool run --from omnigent python -c 'import omnigent,os;print(os.path.join(os.path.dirname(omnigent.__file__),"server","static","web-ui"))' 2>/dev/null)"
fi
[ -n "$PKG_UI" ] || { echo "ERROR: could not locate the active omnigent web-ui dir" >&2; exit 1; }
case "$PKG_UI" in
  */site-packages/omnigent/server/static/web-ui) ;;
  *) echo "ERROR: refusing unexpected web-ui target: $PKG_UI" >&2; exit 1 ;;
esac
echo "==> Serving branded UI from active install: $PKG_UI"
[ -d "$PKG_UI.upstream-bak" ] || cp -R "$PKG_UI" "$PKG_UI.upstream-bak"
rm -rf "$PKG_UI"
cp -R "$FORK_UI" "$PKG_UI"

echo "==> Restarting the Omnigent host service (local server + host)"
omnigent stop --force >/dev/null 2>&1 || true
launchctl kickstart -k "gui/$(id -u)/ai.omnigent.host" 2>/dev/null || true

echo "==> Done. Verify:"
echo "    curl -s http://127.0.0.1:6767/ | grep '<title>'   # expect <title>Deadwax</title>"
TS_NAME="$(tailscale status --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))' 2>/dev/null || true)"
echo "    Phone: https://${TS_NAME:-<host>.<tailnet>.ts.net}:6767  (Tailscale signed in)"
