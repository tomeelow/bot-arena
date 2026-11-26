#!/bin/sh
# Gives the worker's jails a cgroup subtree (the VM's counterpart of sandbox/entrypoint.sh).
# systemd starts the worker in the leaf "main" (DelegateSubgroup), because cgroup v2 lets
# only a cgroup without processes hand controllers to its children; the jails get "bots".
set -eu
unit=$(dirname "/sys/fs/cgroup$(cut -d: -f3 /proc/self/cgroup)")
mkdir -p "$unit/bots"
echo "+cpu +memory +pids" > "$unit/cgroup.subtree_control"
echo "+cpu +memory +pids" > "$unit/bots/cgroup.subtree_control"
ARENA_CGROUP_ROOT="$unit/bots" exec "$@"
