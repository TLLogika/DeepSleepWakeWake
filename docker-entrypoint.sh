#!/bin/sh
set -eu

uid="${WAKEBOARD_UID:-1000}"
gid="${WAKEBOARD_GID:-1000}"

case "$uid" in
    ''|*[!0-9]*) echo "WAKEBOARD_UID musi być liczbą." >&2; exit 1 ;;
esac
case "$gid" in
    ''|*[!0-9]*) echo "WAKEBOARD_GID musi być liczbą." >&2; exit 1 ;;
esac

mkdir -p /app/data
chown -R "$uid:$gid" /app/data
exec gosu "$uid:$gid" "$@"
