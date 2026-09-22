#!/bin/bash
set -e

INSTALL_DIR="/opt/heket"

cd "$INSTALL_DIR"

CURRENT="$(git describe --tags --exact-match HEAD)"

LATEST="$(
    git ls-remote --tags --refs origin |
    awk -F/ '{print $3}' |
    sort -V |
    tail -n 1
)"

[[ -n "$LATEST" ]] || {
    echo "Could not determine latest Heket release."
    exit 1
}

echo "Installed Heket: $CURRENT"
echo "Latest Heket:    $LATEST"

if [[ "$CURRENT" == "$LATEST" ]]; then
    echo "Heket is already current."
    exit 0
fi

echo "Updating Heket $CURRENT -> $LATEST"

git fetch \
    --depth 1 \
    origin \
    "refs/tags/${LATEST}:refs/tags/${LATEST}"

git checkout "$LATEST"

echo "Heket updated to $LATEST"
systemctl restart heket.service