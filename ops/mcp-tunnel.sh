#!/bin/sh
# Starts the Cloudflare quick tunnel to the MCP server (the mcp-tunnel service) and keeps
# MCP_PUBLIC_URL in .env set to its address. Run by ops/tailscale-serve.sh on every deploy,
# before the containers are (re)started, so the MCP server starts with the right address.
#
# Why not Tailscale Funnel: from this server, Funnel's ingress nodes were only reachable through a
# relay with ~1.9 s round trips and lost packets, so each connection took 6-15 s to set up or
# failed, and Claude's connector gave up. Set MCP_TUNNEL=funnel in .env to go back to Funnel.
#
# Exits 0 when the tunnel is in use (prints the connector URL), 1 when it isn't. Never fails a
# deploy.
set -u
cd "$(dirname "$0")/.."

warn() { echo "mcp-tunnel: WARNING: $*" >&2; }
env_value() { sed -n "s/^$1=//p" .env 2>/dev/null | tail -n 1; }
set_env() {
  if grep -qE "^#?$1=" .env; then
    sed -i -E "s|^#?$1=.*|$1=$2|" .env
  else
    echo "$1=$2" >> .env
  fi
}

case ",$(env_value COMPOSE_PROFILES)," in *,mcp,*) ;; *) exit 1 ;; esac
[ "$(env_value MCP_TUNNEL)" = "funnel" ] && exit 1

if ! sudo docker compose up -d mcp-tunnel > /dev/null 2>&1; then
  warn "couldn't start the tunnel; see 'docker compose logs mcp-tunnel'"
  exit 1
fi

port=$(env_value MCP_TUNNEL_METRICS_PORT)
host=""
i=0
while [ $i -lt 45 ]; do
  host=$(curl -s -m 3 "http://127.0.0.1:${port:-20241}/quicktunnel" 2>/dev/null | jq -r '.hostname // empty' 2>/dev/null)
  [ -z "$host" ] && host=$(sudo docker compose logs mcp-tunnel 2>/dev/null \
    | grep -oE '[a-z0-9-]+\.trycloudflare\.com' | tail -n 1)
  [ -n "$host" ] && break
  sleep 2
  i=$((i + 1))
done
if [ -z "$host" ]; then
  warn "the tunnel has no address yet; see 'docker compose logs mcp-tunnel'"
  exit 1
fi

url="https://$host"
if [ "$(env_value MCP_PUBLIC_URL)" != "$url" ]; then
  set_env MCP_PUBLIC_URL "$url"
  echo "mcp-tunnel: NEW ADDRESS: in claude.ai, remove the SmartFin connector and add it again with $url/mcp"
fi
echo "mcp-tunnel: Claude connector at $url/mcp"
exit 0
