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
echo "== health: tailscaled problems, last 2 days (count, then the latest)"
log=$(sudo journalctl -u tailscaled --since "2 days ago" --no-pager -o cat 2>/dev/null \
  | grep -iE 'funnel|ingress|tls|cert|error|fail|timeout|reset')
echo "$log" | grep -c . || true
echo "$log" | tail -n 15 | cut -c1-200 | redact
