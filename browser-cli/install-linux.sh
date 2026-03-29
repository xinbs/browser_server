#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://192.168.31.118:3456}"
CLI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -f "$CLI_DIR/browser-cli" ]]; then
  echo "browser-cli not found under $CLI_DIR" >&2
  exit 1
fi

chmod +x "$CLI_DIR/browser-cli"
SHELL_RC="$HOME/.bashrc"
if [[ -n "${ZSH_VERSION:-}" ]] || [[ "${SHELL##*/}" == "zsh" ]]; then
  SHELL_RC="$HOME/.zshrc"
fi

PATH_LINE="export PATH=\"$CLI_DIR:\$PATH\""
URL_LINE="export BROWSER_SERVER_URL=\"$BASE_URL\""

touch "$SHELL_RC"
TMP_FILE="$(mktemp)"
awk -v path_line="$PATH_LINE" -v url_line="$URL_LINE" '
{
  if ($0 == path_line) next
  if ($0 ~ /^export BROWSER_SERVER_URL=/) next
  if (!inserted && $0 ~ /^[[:space:]]*return([[:space:]].*)?$/) {
    print path_line
    print url_line
    inserted=1
  }
  print
}
END {
  if (!inserted) {
    print path_line
    print url_line
  }
}
' "$SHELL_RC" > "$TMP_FILE"
mv "$TMP_FILE" "$SHELL_RC"

echo "Installed browser-cli PATH at: $CLI_DIR"
echo "Set BROWSER_SERVER_URL=$BASE_URL in $SHELL_RC"
echo "Run: source $SHELL_RC"
echo "Then test: browser-cli health"
