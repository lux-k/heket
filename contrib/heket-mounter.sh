#!/usr/bin/env bash

set -euo pipefail

HEKET_SOURCE_ROOT="/opt/heket-data/recordings/unprocessed"

usage() {
    echo "Usage:" >&2
    echo "  $0 mount <device> <source_id>" >&2
    echo "  $0 umount <source_id>" >&2
    echo >&2
    echo "Examples:" >&2
    echo "  sudo $0 mount mmcblk0p1 3" >&2
    echo "  sudo $0 umount 3" >&2
    exit 2
}

[[ $# -ge 1 ]] || usage

COMMAND="$1"

#
# Must be invoked through sudo by a non-root user.
#
[[ -n "${SUDO_UID:-}" && "$SUDO_UID" != "0" ]] || {
    echo "This command must be invoked through sudo by the Heket user." >&2
    exit 1
}

case "$COMMAND" in

    mount)
        #
        # mount <device> <source_id>
        #
        [[ $# -eq 3 ]] || usage

        DEVICE="$2"
        SOURCE_ID="$3"

        #
        # Only accept a device basename. The caller cannot supply
        # an arbitrary filesystem path.
        #
        [[ "$DEVICE" =~ ^[A-Za-z0-9]+$ ]] || {
            echo "Invalid device name: $DEVICE" >&2
            exit 2
        }

        [[ "$SOURCE_ID" =~ ^[0-9]+$ ]] || {
            echo "Invalid source ID: $SOURCE_ID" >&2
            exit 2
        }

        DEV="/dev/${DEVICE}"
        SOURCE_DIR="${HEKET_SOURCE_ROOT}/${SOURCE_ID}"
        MOUNTPOINT="${SOURCE_DIR}/mount"

        #
        # The supplied device must actually be a block device.
        #
        [[ -b "$DEV" ]] || {
            echo "$DEV is not a block device." >&2
            exit 1
        }

        #
        # Heket must already know about this source. The privileged
        # helper will not manufacture arbitrary source directories.
        #
        [[ -d "$SOURCE_DIR" ]] || {
            echo "Heket source directory does not exist: $SOURCE_DIR" >&2
            exit 1
        }

        mkdir -p "$MOUNTPOINT"

        #
        # Don't mount over an existing filesystem.
        #
        if mountpoint -q "$MOUNTPOINT"; then
            echo "Something is already mounted at $MOUNTPOINT" >&2
            exit 1
        fi

        echo "Mounting $DEV read-only at $MOUNTPOINT for UID $SUDO_UID"

        mount \
            -o "ro,uid=${SUDO_UID}" \
            "$DEV" \
            "$MOUNTPOINT"
        ;;


    umount)
        #
        # umount <source_id>
        #
        # No device is accepted here. The source ID completely
        # determines the only mountpoint this operation may touch.
        #
        [[ $# -eq 2 ]] || usage

        SOURCE_ID="$2"

        [[ "$SOURCE_ID" =~ ^[0-9]+$ ]] || {
            echo "Invalid source ID: $SOURCE_ID" >&2
            exit 2
        }

        SOURCE_DIR="${HEKET_SOURCE_ROOT}/${SOURCE_ID}"
        MOUNTPOINT="${SOURCE_DIR}/mount"

        #
        # The source must already exist.
        #
        [[ -d "$SOURCE_DIR" ]] || {
            echo "Heket source directory does not exist: $SOURCE_DIR" >&2
            exit 1
        }

        #
        # There must actually be something mounted there.
        #
        if ! mountpoint -q "$MOUNTPOINT"; then
            echo "Nothing is mounted at $MOUNTPOINT" >&2
            exit 1
        fi

        #
        # Ask the kernel what the actual mount target is rather
        # than trusting anything supplied by the caller.
        #
        ACTUAL_TARGET="$(findmnt -n -o TARGET --target "$MOUNTPOINT")"

        #
        # Defense in depth: only unmount something living at the
        # Heket source mountpoint convention.
        #
        case "$ACTUAL_TARGET" in
            "${HEKET_SOURCE_ROOT}/"[0-9]*/mount)
                ;;
            *)
                echo "Refusing to unmount target outside Heket namespace: $ACTUAL_TARGET" >&2
                exit 1
                ;;
        esac

        echo "Unmounting $ACTUAL_TARGET"

        umount "$ACTUAL_TARGET"
        ;;


    *)
        usage
        ;;

esac