#!/bin/bash
# Deadwax deploy: build the rebranded ap-web bundle and serve it from the active
# omnigent install on this Mac, then restart the phone-access watchdog.
#
# Our Deadwax customizations are frontend-only (the static web-ui bundle), so we
# build it here and copy it over whatever omnigent the runtime uses — functionally
# identical to running the fork, with none of the dependency-reinstall risk. Run
# this after each weekly upstream sync (or any ap-web change).
set -euo pipefail
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"

FORK_DIR="$(cd "$(dirname "$0")/.." && pwd)"
echo "==> Building rebranded ap-web ($FORK_DIR/ap-web)"
cd "$FORK_DIR/ap-web"
[ -d node_modules ] || npm install --no-audit --no-fund
npm run build   # vite outputs to ../omnigent/server/static/web-ui

FORK_UI="$FORK_DIR/omnigent/server/static/web-ui"
PKG_UI="$(python3 -c 'import omnigent,os;print(os.path.join(os.path.dirname(omnigent.__file__),"server","static","web-ui"))')"
echo "==> Serving branded UI from active install: $PKG_UI"
[ -d "$PKG_UI.upstream-bak" ] || cp -R "$PKG_UI" "$PKG_UI.upstream-bak"
rm -rf "$PKG_UI"
cp -R "$FORK_UI" "$PKG_UI"

echo "==> Restarting the phone-access watchdog"
launchctl kickstart -k "gui/$(id -u)/io.deadwax.omnigent-phone" 2>/dev/null || true

echo "==> Done. Verify:"
echo "    curl -s http://127.0.0.1:6767/ | grep '<title>'   # expect <title>Deadwax</title>"
echo "    Phone: http://100.98.36.83:6767  (Tailscale signed in)"
