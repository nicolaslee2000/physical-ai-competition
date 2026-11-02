#!/bin/sh
set -eu
# Invoked only in a new private mount namespace inside our rootless user namespace.
netns=$1
resolver=$2
shift 2
mount --bind "$resolver" /etc/resolv.conf
exec /usr/bin/nsenter "--net=$netns" "$@"
