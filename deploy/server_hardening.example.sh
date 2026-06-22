#!/usr/bin/env bash
# Example hardening steps for a fresh Ubuntu/Debian VDS (serv.host and similar).
# Review and adapt before running on production.
# Full walkthrough: deploy/VDS_SETUP.md

set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root"
  exit 1
fi

echo "==> Packages: ufw, fail2ban, unattended-upgrades"
apt-get update
apt-get install -y ufw fail2ban unattended-upgrades

echo "==> Firewall (SSH only; bot uses polling — no inbound HTTP ports)"
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
# If you changed SSH port in 50-cloud-init.conf, allow it explicitly, e.g.:
# ufw allow 1337/tcp
# Restrict SSH to your IP only (recommended after key-based login works):
# ufw delete allow OpenSSH
# ufw allow from YOUR.IP.ADDRESS.HERE to any port 22 proto tcp
ufw --force enable

echo "==> Automatic security updates"
dpkg-reconfigure -plow unattended-upgrades

cat <<'EOF'

==> SSH hardening (manual steps — do NOT skip)

1. Change root password: passwd
2. Add your Ed25519 public key to ~/.ssh/authorized_keys
3. Test login in a NEW session before disabling passwords
4. On serv.host / cloud-init images edit:
     /etc/ssh/sshd_config.d/50-cloud-init.conf
   Set: PasswordAuthentication no
   Do NOT rely on /etc/ssh/sshd_config alone — cloud-init overrides it.

5. Restart SSH:
   Ubuntu 22.04: systemctl restart ssh
   Ubuntu 24.04: systemctl daemon-reload && systemctl restart ssh.socket

Details: https://serv.host/articles/23/ and deploy/VDS_SETUP.md

EOF

echo "Base firewall and unattended upgrades configured."
