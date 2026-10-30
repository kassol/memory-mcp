#!/bin/sh
# Start one maintenance run: findings for review; nothing is changed automatically.
# Run from cron on the deploy host. The service runs it in the background. A run already
# in progress makes this call return 409, which is not an error here.
set -eu
cd "$(dirname "$0")/.."

token=$(sed -n 's/^MEMORY_MCP_AUTH_TOKEN=//p' .env)
[ -n "$token" ] || { echo "MEMORY_MCP_AUTH_TOKEN missing in .env" >&2; exit 1; }

out=$(curl -sS -w ' HTTP %{http_code}' -X POST -H "Authorization: Bearer $token" \
  http://127.0.0.1:18765/api/v1/maintenance/run 2>&1) || true
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) maintenance run: $out"
case "$out" in
  *" HTTP 202" | *" HTTP 409") ;;
  *) exit 1 ;;
esac
