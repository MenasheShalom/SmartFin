#!/bin/sh
# Publish SmartFin through Tailscale, the same way every time. Run by deploy.sh on every deploy
# and by cloud-setup.sh; safe to run by hand. The layout follows .env:
#
#   COMPOSE_PROFILES has mcp:  https://<name>        MCP server, public through Funnel
#                              https://<name>:8443   the app, tailnet only
#   otherwise:                 https://<name>        the app, tailnet only
#   BIND_ADDRESS=127.0.0.1:    http://<tailnet IP>:8000   the app, tailnet only, for devices
#                              where the ts.net name doesn't resolve through Tailscale
#
# Claude's connector reaches only the standard HTTPS port, hence the MCP server on 443.
# It never fails a deploy: a problem is printed as a warning and the rest carries on.
set -u
cd "$(dirname "$0")/.."

warn() { echo "tailscale: WARNING: $*" >&2; }
# A first Funnel or HTTPS use can wait for approval in the browser; never hang a deploy on it
ts() { timeout 60 sudo tailscale "$@" || warn "'tailscale $*' failed (see above)"; }
env_value() { sed -n "s/^$1=//p" .env 2>/dev/null | tail -n 1; }

if ! command -v tailscale > /dev/null || ! command -v jq > /dev/null; then
  warn "tailscale or jq is not installed; skipping"
  exit 0
fi
status=$(sudo tailscale status --json 2>/dev/null)
if [ "$(echo "$status" | jq -r '.BackendState // empty')" != "Running" ]; then
  warn "not connected; run 'sudo tailscale up' on the server, then deploy again"
  exit 0
fi
name=$(echo "$status" | jq -r '.Self.DNSName // empty' | sed 's/\.$//')
ip=$(echo "$status" | jq -r '.Self.TailscaleIPs[0] // empty')

with_mcp=false
case ",$(env_value COMPOSE_PROFILES)," in *,mcp,*) with_mcp=true ;; esac

if $with_mcp; then
  mcp_url="https://$name"
  current=$(env_value MCP_PUBLIC_URL)
  if [ -z "$current" ]; then
    if grep -qE '^#?MCP_PUBLIC_URL=' .env; then
      sed -i -E "s|^#?MCP_PUBLIC_URL=.*|MCP_PUBLIC_URL=$mcp_url|" .env
    else
      echo "MCP_PUBLIC_URL=$mcp_url" >> .env
    fi
    echo "tailscale: set MCP_PUBLIC_URL=$mcp_url in .env"
  elif [ "$current" != "$mcp_url" ]; then
    warn "MCP_PUBLIC_URL in .env is $current; Claude reaches this server at $mcp_url"
  fi
fi

# From a clean slate, so nothing set by hand earlier is left on the wrong port
ts serve reset
if $with_mcp; then
  # Funnel puts only the MCP server on the internet
  ts funnel --bg 8001
  ts serve --bg --https=8443 8000
  app_url="https://$name:8443"
else
  ts serve --bg 8000
  app_url="https://$name"
fi

# With BIND_ADDRESS=0.0.0.0 the app already answers on every address, the tailnet's included
if [ "$(env_value BIND_ADDRESS)" = "127.0.0.1" ] && [ -n "$ip" ]; then
  ts serve --bg --tcp=8000 tcp://localhost:8000
  ip_url="http://$ip:8000"
  if [ "$(env_value COOKIE_SECURE)" = "true" ]; then
    warn "logging in at $ip_url needs COOKIE_SECURE=false in .env (Tailscale still encrypts it)"
  fi
fi

echo "tailscale: app at $app_url${ip_url:+ and $ip_url} (tailnet only)"
if $with_mcp; then
  echo "tailscale: Claude connector at https://$name/mcp"
fi
