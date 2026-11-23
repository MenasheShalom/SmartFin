#!/bin/sh
# Keeps Tailscale on the server set up so that Tailscale Funnel (Claude's connector) connects
# quickly. Run by ops/tailscale-serve.sh on every deploy; each step changes nothing when it's
# already done, and nothing here fails a deploy.
#
# Without it, connections through Funnel took 6-8 s to set up and about a third were dropped:
# every peer was reached through a relay, and the first WireGuard handshake from a Funnel
# ingress node was lost, so each connection waited for WireGuard's 5 s retry.
set -u
warn() { echo "tailscale-tune: WARNING: $*" >&2; }
command -v tailscale > /dev/null || exit 0
restart=false

# 1. Up to date: Funnel and relay fixes land in point releases
if command -v apt-get > /dev/null; then
  before=$(tailscale version 2>/dev/null | head -n 1)
  timeout 180 sudo apt-get update -qq -o Dir::Etc::sourcelist=sources.list.d/tailscale.list \
    -o Dir::Etc::sourceparts=- -o APT::Get::List-Cleanup=0 > /dev/null 2>&1 || true
  timeout 300 sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --only-upgrade tailscale \
    > /dev/null 2>&1 || warn "updating tailscale failed"
  after=$(tailscale version 2>/dev/null | head -n 1)
  [ "$before" != "$after" ] && echo "tailscale-tune: updated tailscale $before -> $after"
fi

# 2. Configure every peer in WireGuard up front instead of on its first packet, so a new
#    Funnel ingress node's first handshake isn't dropped
defaults=/etc/default/tailscaled
if [ -f "$defaults" ] && ! grep -q '^TS_DEBUG_TRIM_WIREGUARD=false' "$defaults"; then
  echo 'TS_DEBUG_TRIM_WIREGUARD=false' | sudo tee -a "$defaults" > /dev/null
  echo "tailscale-tune: set TS_DEBUG_TRIM_WIREGUARD=false"
  restart=true
fi

# 3. Let peers reach Tailscale's UDP port directly instead of only through relays (the cloud
#    image's firewall rejects everything but SSH). Oracle's security list must allow it too.
if command -v iptables > /dev/null; then
  if ! sudo iptables -C INPUT -p udp --dport 41641 -j ACCEPT 2> /dev/null; then
    sudo iptables -I INPUT 1 -p udp --dport 41641 -j ACCEPT \
      && echo "tailscale-tune: allowed UDP 41641 in the firewall"
    command -v netfilter-persistent > /dev/null && sudo netfilter-persistent save > /dev/null 2>&1
  fi
fi

if $restart; then
  sudo systemctl restart tailscaled
  echo "tailscale-tune: restarted tailscaled"
fi

# Connected again (after an update or restart) before serve/funnel are set up
i=0
while [ $i -lt 30 ]; do
  state=$(sudo tailscale status --json 2>/dev/null | jq -r '.BackendState // empty')
  [ "$state" = "Running" ] && break
  sleep 2; i=$((i + 1))
done
[ "${state:-}" = "Running" ] || warn "tailscale is not connected (${state:-unknown})"
exit 0
