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
echo "== health: tailscale update"
apt-cache policy tailscale 2>/dev/null | grep -E 'Installed|Candidate'
echo "== health: through Funnel from here (public DNS, then 5 requests)"
name=$(sudo tailscale status --json 2>/dev/null | jq -r '.Self.DNSName // empty' | sed 's/\.$//')
pub=$(curl -s -m 10 -H 'accept: application/dns-json' "https://cloudflare-dns.com/dns-query?name=$name&type=A" \
  | jq -r '[.Answer[]? | select(.type == 1) | .data][0] // empty')
if [ -n "$name" ] && [ -n "$pub" ]; then
  for i in 1 2 3 4 5; do
    curl -s -m 20 -o /dev/null --resolve "$name:443:$pub" \
      -w 'http %{http_code}  tls %{time_appconnect}s  total %{time_total}s\n' "https://$name/health" \
      || echo "failed"
  done
else
  echo "no public address found"
fi
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
