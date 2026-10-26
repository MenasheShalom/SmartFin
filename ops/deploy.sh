#!/bin/sh
# Bring the server up to date with main: pull, publish it through Tailscale (ops/tailscale-serve.sh),
# rebuild what changed, restart.
# Run it on the server by hand, or let the Deploy workflow run it on every push to main (its SSH
# key may run only this script; see "Deploying from GitHub" in the README).
set -eu
cd "$(dirname "$0")/.."
git fetch -q origin main
git merge --ff-only -q origin/main
echo "deploy: $(git log -1 --format='%h %s')"
# Before the restart, since it can fill in MCP_PUBLIC_URL
sh ops/tailscale-serve.sh
sudo docker compose up -d --build --remove-orphans
sudo docker image prune -f > /dev/null
sudo docker compose ps
