#!/bin/sh
# One-time setup of a fresh Debian 13 VM, as root. deploy/RUNBOOK.md has the whole procedure;
# after this, fill in /etc/arena/*.env and run `arena-update <commit sha>`.
set -eu
REPO=https://github.com/tomeelow/bot-arena.git
UV_VERSION=0.11.20

apt-get update
apt-get install -y --no-install-recommends bubblewrap python3-seccomp caddy git curl ca-certificates sqlite3

id arena >/dev/null 2>&1 || useradd --system --home-dir /var/lib/arena --shell /usr/sbin/nologin arena
id deploy >/dev/null 2>&1 || useradd --create-home --shell /bin/sh deploy
# 0711: Caddy may check for the EGRESS_CAPPED flag by name; nobody else may list bot code.
install -d -m 0711 -o arena -g arena /var/lib/arena
install -d -m 0750 -g arena /etc/arena
for f in api caddy backup; do
    [ -e /etc/arena/$f.env ] || install -m 0640 -g arena /dev/null /etc/arena/$f.env
done
chgrp caddy /etc/arena/caddy.env

# A swap file for the API and Caddy; jails have swap turned off (memory.swap.max = 0).
if [ ! -e /swapfile ]; then
    fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab && swapon /swapfile
fi

# Python 3.14 (ADR-001) under /usr, which every jail mounts read-only, so the venv's
# interpreter is visible inside them. Debian 13 ships 3.13.
curl -LsSf "https://astral.sh/uv/$UV_VERSION/install.sh" | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh
UV_PYTHON_INSTALL_DIR=/usr/local/lib/uv-python uv python install 3.14

[ -d /opt/arena/src ] || git clone --quiet "$REPO" /opt/arena/src
install -m 0755 /opt/arena/src/deploy/update.sh /usr/local/sbin/arena-update
install -m 0755 /opt/arena/src/deploy/deploy-ssh.sh /usr/local/sbin/arena-deploy-ssh
echo 'deploy ALL=(root) NOPASSWD: /usr/local/sbin/arena-update' > /etc/sudoers.d/arena-deploy
chmod 0440 /etc/sudoers.d/arena-deploy
install -D -m 0644 /opt/arena/src/deploy/systemd/caddy-override.conf /etc/systemd/system/caddy.service.d/arena.conf
systemctl daemon-reload

echo "Next: fill in /etc/arena/{api,caddy,backup}.env, then: arena-update \$(git -C /opt/arena/src rev-parse origin/main)"
