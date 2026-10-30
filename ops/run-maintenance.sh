#!/bin/sh
# Start one maintenance run (findings for review; nothing is changed automatically).
# Run from cron on the deploy host. The service runs it in the background; a run already
# in progress makes this call return 409, which is not an error here.
set -eu
cd "$(dirname "$0")/.."

token=$(grep '^MEMORY_MCP_AUTH_TOKEN=' .env | cut -d= -f2-)
code=$(curl -s -o /tmp/memory-mcp-maintenance.out -w '%{http_code}' -X POST \
  -H "Authorization: Bearer $token" http://127.0.0.1:18765/api/v1/maintenance/run)
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) maintenance run: HTTP $code $(cat /tmp/memory-mcp-maintenance.out)"
rm -f /tmp/memory-mcp-maintenance.out
[ "$code" = 202 ] || [ "$code" = 409 ]
