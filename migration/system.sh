#!/usr/bin/env bash

set -euo pipefail

version_int() {
    local version="$1"
    awk -v v="$version" 'BEGIN { printf "%d\n", v * 100 }'
}

FROM=$(version_int "$1")
TO=$(version_int "$2")

migrate_026() {
    echo "Applying system migration for .26"
    echo "heket ALL=(root) NOPASSWD: /opt/heket/contrib/heket-mounter.sh *" >> /etc/sudoers.d/heket-mounter
}

for (( version=FROM+1; version<=TO; version++ )); do
    case "$version" in
        26)
            migrate_026
            ;;
    esac
done