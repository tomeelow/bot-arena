#!/bin/sh
# The deploy user's only command over SSH (authorized_keys: restrict,command="arena-deploy-ssh").
# The deploy workflow sends the commit sha as the command; anything else is refused.
set -eu
exec sudo /usr/local/sbin/arena-update "${SSH_ORIGINAL_COMMAND:-}"
