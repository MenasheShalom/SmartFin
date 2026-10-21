#!/usr/bin/env bash
# Set up SmartFin on a fresh Ubuntu cloud server (made for an Oracle Cloud Always Free VM; any
# Ubuntu 22.04/24.04 machine with ~2 GB of RAM works). Run it as the default user, which has sudo:
#
#   curl -fsSL https://raw.githubusercontent.com/MenasheShalom/SmartFin/main/ops/cloud-setup.sh | bash
#   ... or, to also turn on the MCP server for Claude:
#   curl -fsSL https://raw.githubusercontent.com/MenasheShalom/SmartFin/main/ops/cloud-setup.sh | bash -s -- --with-claude
#
# It installs Docker and Tailscale, clones SmartFin to ~/SmartFin, writes .env with fresh secrets,
# starts everything, and serves the app over HTTPS on your tailnet only. Nothing is opened to the
# internet, except the MCP server with --with-claude (through Tailscale Funnel).
# Safe to run again: it keeps an existing .env and data, and pulls and rebuilds.
set -euo pipefail

REPO="${SMARTFIN_REPO:-https://github.com/MenasheShalom/SmartFin.git}"
DIR="${SMARTFIN_DIR:-$HOME/SmartFin}"
WITH_CLAUDE=false
for arg in "$@"; do
  case "$arg" in
    --with-claude) WITH_CLAUDE=true ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

# Set KEY=VALUE in .env, replacing a commented or uncommented line, or adding one
set_env() {
  local key="$1" value="$2"
  if grep -qE "^#?${key}=" .env; then
    sed -i -E "s|^#?${key}=.*|${key}=${value}|" .env
  else
    printf '%s=%s\n' "$key" "$value" >> .env
  fi
}

step "Installing Docker, Git and updates"
sudo apt-get update -q
sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade -yq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -yq docker.io docker-compose-v2 git jq openssl
sudo systemctl enable --now docker

# Chromium (the scraper), Postgres and the builds need room; small VMs get swap
mem_mb=$(awk '/MemTotal/ {print int($2 / 1024)}' /proc/meminfo)
if [ "$mem_mb" -lt 3000 ] && ! swapon --show | grep -q .; then
  step "Adding 2 GB of swap (this machine has ${mem_mb} MB of RAM)"
  sudo fallocate -l 2G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab > /dev/null
fi

step "Installing Tailscale"
if ! command -v tailscale > /dev/null; then
  curl -fsSL https://tailscale.com/install.sh | sh
fi
if ! sudo tailscale status > /dev/null 2>&1; then
  echo "Open the link below and sign in to add this server to your tailnet:"
  # TS_AUTHKEY skips the browser sign-in (an auth key from the Tailscale admin console)
  sudo tailscale up --ssh=false ${TS_AUTHKEY:+--auth-key="$TS_AUTHKEY"}
fi
ts_name=$(sudo tailscale status --json | jq -r '.Self.DNSName' | sed 's/\.$//')

step "Getting SmartFin into $DIR"
if [ -d "$DIR/.git" ]; then
  git -C "$DIR" pull --ff-only
else
  git clone "$REPO" "$DIR"
fi
cd "$DIR"

if [ ! -f .env ]; then
  step "Writing .env with new secrets"
  cp .env.example .env
  chmod 600 .env
  set_env POSTGRES_PASSWORD "$(openssl rand -hex 32)"
  set_env INGEST_TOKEN "$(openssl rand -hex 32)"
  # Only Tailscale reaches the app, over HTTPS
  set_env BIND_ADDRESS 127.0.0.1
  set_env COOKIE_SECURE true
else
  echo ".env already exists; keeping it"
fi

if $WITH_CLAUDE; then
  set_env COMPOSE_PROFILES mcp
  set_env MCP_PUBLIC_URL "https://${ts_name}:8443"
fi

step "Building and starting SmartFin (the first build takes several minutes)"
sudo docker compose up -d --build

step "Serving the app on your tailnet"
# If HTTPS certificates are off for the tailnet, this prints a link to turn them on; then run
# the script again.
sudo tailscale serve --bg 8000
if $WITH_CLAUDE; then
  # Funnel puts only the MCP server on the internet; it asks to be enabled the first time
  sudo tailscale funnel --bg --https=8443 8001
fi

step "Done"
cat <<EOF
SmartFin:      https://${ts_name}
               (from any device signed in to your Tailscale account)
EOF
if $WITH_CLAUDE; then
  cat <<EOF
Claude:        add a custom connector at claude.ai with the URL
               https://${ts_name}:8443/mcp
EOF
fi
cat <<EOF

Next: open SmartFin and create your login straight away, then add your bank and card logins
under הגדרות › חשבונות וסנכרון.
Status:        cd $DIR && sudo docker compose ps
Logs:          cd $DIR && sudo docker compose logs -f scraper
Update later:  run this script again
EOF
