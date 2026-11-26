#!/bin/sh
# Deploys one commit, as root: `arena-update <full sha>`. A rollback is the same command with
# an older sha. The GitHub deploy workflow calls it over SSH (deploy-ssh.sh).
set -eu
sha=${1:-}
case "$sha" in
    *[!0-9a-f]* | "") echo "usage: arena-update <40-character commit sha>" >&2; exit 2 ;;
esac
[ ${#sha} -eq 40 ] || { echo "usage: arena-update <40-character commit sha>" >&2; exit 2; }

src=/opt/arena/src
git -C $src fetch --quiet origin
git -C $src checkout --quiet --detach "$sha"
cd $src
UV_PROJECT_ENVIRONMENT=/opt/arena/venv UV_PYTHON_INSTALL_DIR=/usr/local/lib/uv-python \
    UV_PYTHON_DOWNLOADS=never UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    uv sync --quiet --locked --all-packages --no-dev --no-editable --python 3.14
python3 sandbox/seccomp_policy.py /opt/arena/seccomp.bpf
chmod -R a+rX /opt/arena/venv /opt/arena/seccomp.bpf

install -m 0644 deploy/systemd/*.service deploy/systemd/*.timer /etc/systemd/system/
install -m 0644 deploy/Caddyfile /etc/caddy/Caddyfile
install -m 0755 deploy/update.sh /usr/local/sbin/arena-update
install -m 0755 deploy/deploy-ssh.sh /usr/local/sbin/arena-deploy-ssh
systemctl daemon-reload
runuser -u arena -- env ARENA_DATA_DIR=/var/lib/arena /opt/arena/venv/bin/python -m arena_server.ops bootstrap
# A match cut off here is voided by the reaper and queued again; it is never rated.
systemctl enable --quiet arena-api arena-scheduler arena-worker@1 arena-guard.timer arena-backup.timer
systemctl restart arena-api arena-scheduler arena-worker@1
systemctl start arena-guard.timer arena-backup.timer
systemctl reload-or-restart caddy
echo "$sha" > /opt/arena/deployed
echo "deployed $sha"
