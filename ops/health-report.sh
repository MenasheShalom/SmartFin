#!/bin/sh
# A short report on the server's health, printed on every deploy (from ops/tailscale-serve.sh) to
# help when the app or Claude's connector is slow or drops connections. The Deploy workflow's log
# is public for a public repository, so it prints no addresses, machine names or keys.
# It never fails a deploy.
set -u

# Hide IPv4/IPv6 addresses and hex keys in anything taken from logs
redact() { sed -E 's/[0-9]{1,3}(\.[0-9]{1,3}){3}(:[0-9]+)?/<ip>/g; s/\[?[0-9a-fA-F]{0,4}(:[0-9a-fA-F]{0,4}){2,7}\]?(:[0-9]+)?/<ip>/g; s/[0-9a-f]{16,}/<key>/g; s/[A-Za-z0-9-]+\.[A-Za-z0-9-]+\.ts\.net/<name>/g'; }

echo "== health: uptime and load"
uptime
echo "== health: memory (MB)"
free -m
echo "== health: disk"
df -h / | tail -n 1
echo "== health: containers"
timeout 30 sudo docker stats --no-stream --format '{{.Name}}  cpu {{.CPUPerc}}  mem {{.MemUsage}}' 2>&1
echo "== health: out-of-memory kills, last 7 days"
sudo journalctl -k --since "7 days ago" --no-pager -o cat 2>/dev/null \
  | grep -iE 'out of memory|oom-kill|killed process' | tail -n 10 | redact
echo "== health: tailscale"
tailscale version 2>/dev/null | head -n 1
timeout 30 sudo tailscale netcheck 2>&1 | grep -E 'UDP:|IPv4:|IPv6:|MappingVaries|Nearest DERP' \
  | sed -E 's/(IPv[46]:[^,(]*).*/\1/' | redact
echo "== health: tailscale health warnings"
sudo tailscale status --json 2>/dev/null | jq -r '.Health[]? // empty' | redact
echo "== health: tailnet lock"
timeout 20 sudo tailscale lock status 2>&1 | grep -viE '^\s*$' | grep -vE 'tlpub:|nlpub:|nodekey:' | head -n 8 | redact
echo "== health: peer paths (online peers)"
sudo tailscale status --json 2>/dev/null | jq -c '[.Peer[]? | select(.Online)
  | if (.CurAddr // "") != "" then "direct" elif (.Relay // "") != "" then "relay:" + .Relay else "idle" end]
  | group_by(.) | map({(.[0]): length}) | add'
echo "== health: firewall INPUT rules"
sudo iptables -S INPUT 2>/dev/null | head -n 12 | redact
echo "== health: tailscale update"
apt-cache policy tailscale 2>/dev/null | grep -E 'Installed|Candidate'
echo "== health: Claude's address, from here (5 requests)"
pub_url=$(sed -n 's/^MCP_PUBLIC_URL=//p' .env 2>/dev/null | tail -n 1)
if [ -n "$pub_url" ]; then
  for i in 1 2 3 4 5; do
    curl -s -m 20 -o /dev/null \
      -w 'http %{http_code}  tcp %{time_connect}s  tls %{time_appconnect}s  total %{time_total}s\n' "$pub_url/health" \
      || echo "failed"
  done
else
  echo "MCP_PUBLIC_URL is not set"
fi
echo "== health: what Claude's connector sees at that address"
if [ -n "$pub_url" ]; then
  # /mcp without a token: 401, pointing at the sign-in metadata
  curl -s -m 20 -o /dev/null -D - -X POST "$pub_url/mcp" -H 'content-type: application/json' \
    -H 'accept: application/json, text/event-stream' -d '{"jsonrpc":"2.0","id":1,"method":"initialize"}' \
    | grep -iE '^HTTP/|^www-authenticate' | tr -d '\r'
  curl -s -m 20 "$pub_url/.well-known/oauth-protected-resource/mcp" | jq -c '{resource, authorization_servers}'
  curl -s -m 20 "$pub_url/.well-known/oauth-authorization-server" | jq -c '{issuer, authorization_endpoint, registration_endpoint}'
fi
echo "== health: Claude's whole path, signed in (initialize, list tools, call a tool)"
timeout 90 sudo docker compose exec -T mcp python - < ops/mcp-check.py 2>&1 | tail -n 6
echo "== health: the MCP server directly (3 requests)"
for i in 1 2 3; do
  curl -s -m 20 -o /dev/null -w 'local  http %{http_code}  total %{time_total}s\n' http://127.0.0.1:8001/health || echo "failed"
done
echo "== health: active peers (path)"
sudo tailscale status --json 2>/dev/null | jq -r '.Peer[]? | select(.Active)
  | "\(.OS // "?") tags=\((.Tags // []) | join(",")) relay=\(.Relay // "") direct=\(if (.CurAddr // "") != "" then "yes" else "no" end) rx=\(.RxBytes) tx=\(.TxBytes)"' | head -n 20
echo "== health: tunnel log (last lines)"
sudo docker compose logs --no-log-prefix --tail 8 mcp-tunnel 2>/dev/null | cut -c1-200 | redact
echo "== health: tailscaled log, last 6 hours (counts)"
log6=$(sudo journalctl -u tailscaled --since "6 hours ago" --no-pager -o cat 2>/dev/null)
for pat in 'TLS handshake error' 'invalid-packet-filter' 'netmap' 'derp' 'magicsock' 'wg: '; do
  printf '%s: %s\n' "$pat" "$(echo "$log6" | grep -c -- "$pat")"
done
echo "== health: tailscaled problems, last 2 days (count, then the latest)"
log=$(sudo journalctl -u tailscaled --since "2 days ago" --no-pager -o cat 2>/dev/null \
  | grep -iE 'funnel|ingress|tls|cert|error|fail|timeout|reset')
echo "$log" | grep -c . || true
echo "$log" | tail -n 15 | cut -c1-200 | redact
