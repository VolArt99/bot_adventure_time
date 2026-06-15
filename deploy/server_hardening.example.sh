#!/usr/bin/env bash
# Example hardening steps for a fresh Ubuntu/Debian VDS.
# Review and adapt before running on production.

set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root"
  exit 1
fi

apt-get update
apt-get install -y ufw fail2ban unattended-upgrades

ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
# Uncomment if you need SSH from a fixed IP only:
# ufw delete allow OpenSSH
# ufw allow from YOUR.IP.ADDRESS.HERE to any port 22 proto tcp
ufw --force enable

dpkg-reconfigure -plow unattended-upgrades

echo "Base firewall and unattended upgrades configured."
