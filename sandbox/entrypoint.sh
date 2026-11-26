#!/bin/sh
# Gives the jails a cgroup subtree. cgroup v2 forbids processes in a cgroup whose children
# get controllers, so everything already running moves into a leaf first.
set -eu
cg=/sys/fs/cgroup
mkdir -p "$cg/init" "$ARENA_CGROUP_ROOT"
for pid in $(cat "$cg/cgroup.procs"); do
    echo "$pid" > "$cg/init/cgroup.procs" 2>/dev/null || true
done
echo "+cpu +memory +pids" > "$cg/cgroup.subtree_control"
echo "+cpu +memory +pids" > "$ARENA_CGROUP_ROOT/cgroup.subtree_control"
exec "$@"
