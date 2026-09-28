#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    printf 'Run with sudo: sudo ./install.sh\n' >&2
    exit 1
fi

target_user=${1:-${SUDO_USER:-}}
if [ -z "$target_user" ] || [ "$target_user" = root ]; then
    printf 'Provide the desktop user via sudo or as the first argument.\n' >&2
    exit 1
fi
if ! id "$target_user" >/dev/null 2>&1; then
    printf 'Unknown user: %s\n' "$target_user" >&2
    exit 1
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if ! getent group ocypus-a62 >/dev/null; then
    if ! command -v groupadd >/dev/null 2>&1; then
        printf 'groupadd is required to create the ocypus-a62 device group.\n' >&2
        exit 1
    fi
    groupadd --system ocypus-a62
fi
install -D -o root -g root -m 0755 "$script_dir/ocypus_a62.py" /usr/local/libexec/ocypus_a62.py
install -D -o root -g root -m 0644 "$script_dir/99-ocypus-a62.rules" /etc/udev/rules.d/99-ocypus-a62.rules
install -D -o root -g root -m 0644 "$script_dir/ocypus-a62@.service" /etc/systemd/system/ocypus-a62@.service
udevadm control --reload-rules
udevadm trigger --subsystem-match=hidraw
udevadm settle
systemctl daemon-reload
systemctl enable "ocypus-a62@${target_user}.service"
systemctl restart "ocypus-a62@${target_user}.service"
printf 'Installed and started ocypus-a62@%s.service\n' "$target_user"
