#!/bin/sh
# Runs deploy/Caddyfile in the Caddy version Debian 13 ships and checks who gets through:
# strangers get 403, the Pages proxy reaches the API, and the egress cap turns it into 503.
set -eu
image=caddy:2.6.2-alpine
flags=$(mktemp -d)
name=arena-caddy-check-$$
trap 'docker rm -f $name >/dev/null 2>&1 || true; rm -rf "$flags"' EXIT
docker run -d --name $name -p 127.0.0.1::8080 -v "$PWD/deploy/Caddyfile:/etc/caddy/Caddyfile:ro" \
    -v "$flags:/var/lib/arena:ro" -e ARENA_HOST=http://:8080 -e ARENA_ORIGIN_SECRET=s3cret \
    $image >/dev/null
url=http://$(docker port $name 8080)
status() { curl -s -o /dev/null -w '%{http_code}' "$@"; }
for _ in $(seq 50); do [ "$(status "$url/health")" != 000 ] && break; sleep 0.1; done
expect() { got=$(status "$@"); [ "$got" = "$want" ] || { echo "caddy: $* gave $got, want $want"; exit 1; }; }
want=502 expect "$url/health"                             # proxied (no API running here)
want=403 expect "$url/api/ladder"
want=403 expect -H 'X-Arena-Origin: wrong' "$url/api/ladder"
want=502 expect -H 'X-Arena-Origin: s3cret' "$url/api/ladder"
touch "$flags/EGRESS_CAPPED"
want=503 expect -H 'X-Arena-Origin: s3cret' "$url/api/ladder"
echo "caddy: ok"
