#!/usr/bin/env bash
#v.01

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
INSTALL_BASE="/opt"
INSTALL_DIR="${INSTALL_BASE}/heket"
DATA_DIR="${INSTALL_BASE}/heket-data"
VENV_DIR="${INSTALL_BASE}/heket-env"
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
        git ls-remote --tags --refs "$REPO" |
        awk -F/ '{print $3}' |
        sort -V |
        tail -n 1
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

mkdir "${DATA_DIR}"
chown -R "${HEKET_USER}:${HEKET_USER}" "${DATA_DIR}"
ln -s "${DATA_DIR}" "${INSTALL_DIR}/data"

#
# Python environment
#

info "Creating Python environment..."

python3 -m venv "${VENV_DIR}"

"${VENV_DIR}/bin/python" -m pip install --upgrade pip
"${VENV_DIR}/bin/python" -m pip install -r "${INSTALL_DIR}/requirements.txt"

cp "${INSTALL_DIR}/contrib/heket.service" /etc/systemd/system/heket.service

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

echo
echo "Visit Heket to get started:"
echo "  http://$(hostname):5000/"
echo "  http://$(hostname).local:5000/"
echo

echo "To see logs:"
echo "  journalctl -u heket -n 100 -f"