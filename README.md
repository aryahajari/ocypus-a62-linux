# Ocypus Iota A62 CPU temperature display for Linux

Show your CPU temperature on the **Ocypus Iota A62** cooler's two-digit display. This small Python program reads Linux hardware sensors and sends the temperature through the cooler's USB HID interface. It uses only the Python standard library; no package manager or Python dependencies are needed.

The service updates the display automatically after boot. It does not control fans, pump speed, power limits, or thermal protection.

## Compatibility

- **Cooler:** Ocypus Iota A62 with USB ID `1a2c:434d` and a compatible HID interface. Other models and hardware revisions are not confirmed.
- **System:** Linux with Python 3.9 or newer, udev, and systemd. The installer also uses standard `install`, `getent`, and `groupadd` commands.
- **CPU sensor:** Intel `coretemp` with numbered `Core N` readings, or AMD `k10temp` with `Tdie` or `Tctl`.

On Intel, the display shows the average of the numbered core readings, excluding the package reading. On AMD, it uses `Tdie` if available, otherwise `Tctl`. Values are rounded to whole degrees Celsius and limited to the display's `00`–`99` range. The unit indicator is set to Celsius.

This setup has been checked on Ubuntu 26.04 with an Intel CPU and the listed A62 USB device. AMD sensor handling is covered by automated tests but has not been checked on a physical AMD system.

## Quick start

1. Connect the cooler's USB cable to an internal USB header. Clone this repository:

   ```sh
   git clone https://github.com/aryahajari/ocypus-a62-linux.git
   cd ocypus-a62-linux
   ```

2. Check that both the display and a supported CPU sensor are visible. This command only reads information; it does not write to the display:

   ```sh
   python3 ocypus_a62.py status
   ```

   It should print a `/dev/hidraw*` path, the sensor source, and a 64-byte report. If it fails, see [Troubleshooting](#troubleshooting) before installing.

3. Install and start the service:

   ```sh
   sudo ./install.sh
   systemctl status "ocypus-a62@$(id -un).service" --no-pager
   ```

   The installer creates a dedicated `ocypus-a62` device group, installs a rule for the display interface, copies the program and service to system locations, then enables and starts the service for your account. It is safe to run again when updating the program. If running the installer from a root shell, pass the account name explicitly: `./install.sh your-user-name`.

The service runs as your user with access to the display interface through the dedicated group. It sends a new report when the shown temperature changes and a keepalive every two seconds. If the USB connection or sensor disappears, it logs the error and tries again.

## Everyday use

The display updates automatically while the service is running and after reboot. To check it or see errors:

```sh
systemctl status "ocypus-a62@$(id -un).service" --no-pager
journalctl -u "ocypus-a62@$(id -un).service" -b --no-pager
```

To stop or resume updates:

```sh
sudo systemctl stop "ocypus-a62@$(id -un).service"
sudo systemctl start "ocypus-a62@$(id -un).service"
```

To update an installation, run `git pull` in the cloned directory, then `sudo ./install.sh` again.

## Troubleshooting

**`Ocypus A62 HID interface was not found`** — Check the cooler's USB connection. If `lsusb` is available, `lsusb -d 1a2c:434d` should list the device. A different USB ID or report layout is outside the current compatibility range. The program deliberately matches the display interface rather than the keyboard interface exposed by the same controller.

**`No supported CPU temperature sensor found`** — Check `ls /sys/class/hwmon/hwmon*/name` and the corresponding `temp*_label` files. Intel systems need the `coretemp` kernel module and numbered `Core N` labels; AMD systems need `k10temp` and a `Tdie` or `Tctl` label. You may need to load the appropriate kernel module or enable hardware monitoring in firmware.

**`Permission denied`** — The service should receive access through the udev rule and its supplementary group. Re-run `sudo ./install.sh`, then check `ls -l /dev/hidraw*` and the service journal. An ordinary `python3 ocypus_a62.py once` command from your shell does not receive the service's group automatically. For a single manual update after installation, use:

```sh
sudo -u "$(id -un)" -g ocypus-a62 python3 /usr/local/libexec/ocypus_a62.py once
```

**Service starts but the display stays blank** — Check the service journal and run `python3 ocypus_a62.py status`. Confirm that the USB ID matches. Report values are shown in Celsius and limited to two digits. If the service is active with no errors but the display is still blank, this controller revision may use a different protocol.

## Remove

Run these commands for the account used at installation:

```sh
sudo systemctl disable --now "ocypus-a62@$(id -un).service"
sudo rm /etc/systemd/system/ocypus-a62@.service /etc/udev/rules.d/99-ocypus-a62.rules /usr/local/libexec/ocypus_a62.py
sudo systemctl daemon-reload
sudo udevadm control --reload-rules
```

The dedicated `ocypus-a62` group can be removed with `sudo groupdel ocypus-a62` if it is no longer in use. Reconnect the cooler or trigger udev after removing the rule to restore default device permissions.

## How it works

The controller exposes USB ID `1a2c:434d` as a “USB Gaming Keyboard.” The program selects HID interface `01` by its report descriptor and sends a 64-byte feature report with ID `07`. Bytes 4 and 5 carry the tens and ones digits, and byte 7 selects Celsius. The USB report layout follows the [A62 Linux protocol work](https://github.com/Muyoouu/ocypus-a62-digital-linux).

## Development

Run the standard-library tests with `python3 -m unittest discover -s tests -v`. Contributions that add confirmed device revisions or sensor types are welcome; include the hardware details and a focused test. See [LICENSE](LICENSE) for the MIT license.
