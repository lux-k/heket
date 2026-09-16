#!/usr/bin/env bash

set -euo pipefail

#
# Heket installer
#
# Usage:
#   sudo bash install-pi.sh
#   sudo bash install-pi.sh v0.21
#

REPO="https://github.com/lux-k/heket.git"
GITHUB_REPO="lux-k/heket"
INSTALL_DIR="/opt/heket"
HEKET_USER="heket"

REQUESTED_VERSION="${1:-latest}"


#
# Helpers
#

die()
{
    echo "ERROR: $*" >&2
    exit 1
}

info()
{
    echo "==> $*"
}


#
# Sanity checks
#

if [[ $EUID -ne 0 ]]; then
    die "This installer must be run as root."
fi

ARCH="$(uname -m)"

#
# Basic dependencies needed by the installer itself
#

info "Installing bootstrap dependencies..."

apt-get update
apt-get install -y \
    ca-certificates \
    curl \
    git \
    python3 \
    python3-venv \
    ffmpeg

#
# Resolve Heket version
#

if [[ "$REQUESTED_VERSION" == "latest" ]]; then

    info "Finding latest Heket release..."

    VERSION="$(
        curl -fsSL \
            "https://api.github.com/repos/${GITHUB_REPO}/releases/latest" |
        python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"])'
    )"

    [[ -n "$VERSION" ]] || die "Could not determine latest Heket release."

else

    VERSION="$REQUESTED_VERSION"

    info "Checking Heket release ${VERSION}..."

    if ! git ls-remote \
        --exit-code \
        --tags \
        "$REPO" \
        "refs/tags/${VERSION}" >/dev/null 2>&1
    then
        die "Heket release ${VERSION} does not exist."
    fi
fi


echo
echo "Heket Installer"
echo
echo "Architecture:  ${ARCH}"
echo "Version:       ${VERSION}"
echo "Install path:  ${INSTALL_DIR}"
echo

exit 0

#
# Don't accidentally trash an existing installation
#

if [[ -e "$INSTALL_DIR" ]]; then
    die "${INSTALL_DIR} already exists. Refusing to overwrite it."
fi


#
# Create service account if necessary
#

if ! id "$HEKET_USER" >/dev/null 2>&1; then
    info "Creating Heket service account..."

    useradd \
        --system \
        --create-home \
        --shell /usr/sbin/nologin \
        "$HEKET_USER"
fi


#
# Fetch exactly the requested release
#

info "Installing Heket ${VERSION}..."

git clone \
    --branch "$VERSION" \
    --depth 1 \
    "$REPO" \
    "$INSTALL_DIR"

mkdir "/opt/{$INSTALL_DIR}/heket-data
chown -R "${HEKET_USER}:${HEKET_USER}" "${INSTALL_DIR}/heket-data"
ln -s "${INSTALL_DIR}/heket-data" "${INSTALL_DIR}/heket/data"

#
# Python environment
#

info "Creating Python environment..."

python3 -m venv "${INSTALL_DIR}/heket-env"

"${INSTALL_DIR}/heket-env/bin/python" -m pip install --upgrade pip
"${INSTALL_DIR}/heket-env/bin/python" -m pip install -r "${INSTALL_DIR}/requirements.txt"

cp /opt/heket/contrib/heket.service /etc/systemd/system/heket.service

systemctl daemon-reload
systemctl enable --now heket

echo
echo "----------------------------------------"
echo " Heket ${VERSION} installed successfully"
echo "----------------------------------------"
echo
echo "Installation directory:"
echo "  ${INSTALL_DIR}"
echo
echo "🐸 Ready for frogs."
echo