#!/bin/sh
# Bring the server up to date with main: pull, publish it through Tailscale (ops/tailscale-serve.sh),
# rebuild what changed, restart.
# Run it on the server by hand, or let the Deploy workflow run it on every push to main (its SSH
# key may run only this script; see "Deploying from GitHub" in the README).
set -eu
cd "$(dirname "$0")/.."

# The workflow's "backfill" action (sent as the SSH command, which the key's forced command
# hands over here): sync every login as far back as a new login goes, in the background, since
# years of history take a while. Records already stored are skipped.
if [ "${SSH_ORIGINAL_COMMAND:-}" = "backfill" ]; then
  sudo docker rm -f smartfin-backfill > /dev/null 2>&1 || true
  sudo docker compose run -d --name smartfin-backfill scraper npm run scrape-once -- --full-history
  echo "backfill: started; on the server, follow it with: sudo docker logs -f smartfin-backfill"
  exit 0
fi
git fetch -q origin main
git merge --ff-only -q origin/main
echo "deploy: $(git log -1 --format='%h %s')"
# Before the restart, since it can fill in MCP_PUBLIC_URL
sh ops/tailscale-serve.sh
sudo docker compose up -d --build --remove-orphans
sudo docker image prune -f > /dev/null
sudo docker compose ps
