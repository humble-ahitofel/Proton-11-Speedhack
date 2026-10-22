#!/bin/sh
# Applies the Proton SpeedHack Wine patches to Valve's pinned wine submodule.
#
# Usage: patches/apply-wine-patches.sh [--check]
#
# The script is idempotent: patches that are already applied are skipped.
# With --check it only reports whether every patch is applied or applicable.
#
# Generated files (include/wine/server_protocol.h, server/request_*.h,
# dlls/ntdll/ntsyscalls.h, configure) are intentionally not part of the
# patches; Proton's build system regenerates them (see make/rules-wine-requests.mk).

set -eu

top=$(cd "$(dirname "$0")/.." && pwd)
wine="$top/wine"
check_only=0
[ "${1:-}" = "--check" ] && check_only=1

if [ ! -f "$wine/server/protocol.def" ]; then
    echo "error: $wine is not checked out, run: git submodule update --init --recursive wine" >&2
    exit 1
fi

status=0
for patch in "$top"/patches/wine/*.patch; do
    name=$(basename "$patch")
    if git -C "$wine" apply --check -R "$patch" >/dev/null 2>&1; then
        echo "already applied: $name"
    elif git -C "$wine" apply --check "$patch" >/dev/null 2>&1; then
        if [ $check_only = 1 ]; then
            echo "applicable:      $name"
        else
            git -C "$wine" apply --whitespace=nowarn "$patch"
            echo "applied:         $name"
        fi
    else
        echo "error: $name does not apply to wine $(git -C "$wine" rev-parse --short HEAD)" >&2
        git -C "$wine" apply --check -v "$patch" >&2 || true
        status=1
    fi
done
exit $status
