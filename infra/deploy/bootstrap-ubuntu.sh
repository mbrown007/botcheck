#!/usr/bin/env bash
# BotCheck Ubuntu Hardening & Bootstrap Script
# Run this on a fresh Ubuntu 24.04/22.04 DigitalOcean Droplet as root.

set -euo pipefail

echo "==========================================="
echo "  Hardening & Bootstrapping Droplet...     "
echo "==========================================="

# 1. Update system
apt-get update && apt-get upgrade -y

# 2. Install dependencies
apt-get install -y fail2ban ufw curl wget git rsync

# 3. Harden SSH (Disable password authentication)
echo "Hardening SSH..."
sed -i -e 's/#PasswordAuthentication yes/PasswordAuthentication no/g' /etc/ssh/sshd_config
sed -i -e 's/PasswordAuthentication yes/PasswordAuthentication no/g' /etc/ssh/sshd_config
systemctl restart ssh

# 4. Configure fail2ban
echo "Configuring fail2ban..."
cat <<EOF > /etc/fail2ban/jail.local
[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 3600
EOF
systemctl restart fail2ban

# 5. Configure UFW (Firewall)
echo "Configuring UFW..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing

# Standard Web/SSH
ufw allow 22/tcp      # SSH
ufw allow 80/tcp      # HTTP
ufw allow 443/tcp     # HTTPS
ufw allow 7700/tcp    # API (Change to 443 if using a reverse proxy)
ufw allow 9100/tcp    # Node Exporter (Host Metrics)

# LiveKit Media/Signaling
ufw allow 7880/tcp    # LiveKit API/Signaling
ufw allow 7881/tcp    # LiveKit TURN
ufw allow 7882/udp    # LiveKit TURN

# SIP Trunk / WebRTC (LiveKit SIP)
ufw allow 5060/tcp
ufw allow 5060/udp
ufw allow 5061/tcp
ufw allow 10000:20000/udp

ufw --force enable

# 6. Install Docker & Docker Compose
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    rm get-docker.sh
fi

systemctl enable docker
systemctl start docker

echo "==========================================="
echo "  Bootstrap Complete!                      "
echo "  Droplet is hardened and ready for code.  "
echo "==========================================="
