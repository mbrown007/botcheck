#!/usr/bin/env bash
# Local Deployment Script
# Syncs your local BotCheck directory to the droplet and restarts the stack.
#
# Usage: ./infra/deploy/deploy.sh root@<your-droplet-ip>

set -euo pipefail

if [ -z "${1:-}" ]; then
  echo "Usage: $0 root@<droplet-ip>"
  exit 1
fi

DEST="$1"
REMOTE_DIR="/opt/botcheck"

echo "Syncing code to $DEST:$REMOTE_DIR..."

# Use rsync to copy the repo, excluding node_modules, Python environments, and Git history.
rsync -avz --delete \
  --exclude '.git' \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude 'node_modules' \
  --exclude '.next' \
  --exclude 'infra/localstack' \
  --exclude '.localstack' \
  ./ "$DEST:$REMOTE_DIR"

echo "Restarting Docker Compose stack on remote server..."

ssh "$DEST" << 'EOF'
  cd /opt/botcheck

  # Ensure the .env file exists (if not, copy from example)
  if [ ! -f .env ]; then
    echo "Creating .env from .env.example. PLEASE UPDATE CREDENTIALS in /opt/botcheck/.env"
    cp .env.example .env
  fi

  # Pull latest images and restart stack
  docker compose pull
  docker compose down
  docker compose up -d --build
  
  # Remove any unused images/containers to save droplet space
  docker system prune -f
EOF

echo "Deployment complete!"
