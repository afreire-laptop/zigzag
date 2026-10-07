#!/bin/sh
# Hardening checks for a running Compose stack, called by docker-smoke.sh from the stack's directory.
#   sh scripts/smoke_hardening.sh <compose-project> <web-port>
# Every check either prints "ok" or prints FAIL and exits 1, so a regression fails the smoke test.
set -eu
project="$1"
port="$2"

fail() {
  echo "FAIL $1" >&2
  exit 1
}

api_uid="$(docker compose -p "$project" exec -T api id -u)"
[ "$api_uid" = "10001" ] || fail "the API runs as a non-root user (uid: $api_uid)"
echo "ok   the API runs as a non-root user"

web_uid="$(docker compose -p "$project" exec -T web id -u)"
[ "$web_uid" = "101" ] || fail "nginx runs as a non-root user (uid: $web_uid)"
echo "ok   nginx runs as a non-root user"

api_ports="$(docker compose -p "$project" ps api --format '{{.Ports}}')"
case "$api_ports" in *"->"*) fail "the API is not published to the host (published: $api_ports)" ;; esac
echo "ok   the API is not published to the host"

docker compose -p "$project" exec -T web nginx -T 2>/dev/null | awk '/operations\/\[\^\/\]\+\/events/,/}/' \
  | grep -q "proxy_buffering off" || fail "nginx does not buffer the event stream"
echo "ok   nginx does not buffer the event stream"

docker compose -p "$project" ps --format '{{.Service}} {{.Ports}}' | grep -q "127.0.0.1:$port->8080" \
  || fail "the web entry point is bound to 127.0.0.1"
echo "ok   the web entry point is bound to 127.0.0.1"
