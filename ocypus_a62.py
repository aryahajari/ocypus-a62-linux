#!/usr/bin/env python3
"""Show the average CPU core temperature on an Ocypus Iota A62 display.

Uses only the Python standard library and Linux's hidraw interface. It does not
control the cooler fans or motherboard thermal protection.
"""

import argparse
import fcntl
import math
import os
from pathlib import Path
import signal
import sys
import time


VID = "1a2c"
PID = "434d"
INTERFACE = "01"
REPORT_ID = 0x07
REPORT_LENGTH = 64  # report ID + 63-byte feature payload
SYS_HIDRAW = Path("/sys/class/hidraw")
SYS_HWMON = Path("/sys/class/hwmon")

# The report descriptor observed on this machine declares a vendor collection,
# report ID 7, and a 63-byte Feature report on USB HID interface 1.
FEATURE_DESCRIPTOR = bytes.fromhex("85 07 09 03 15 00 26 ff 00 75 08 95 3f b1 02")


def build_report(temp_c: float) -> bytes:
    """Encode an integer temperature in the A62's two-digit Celsius format."""
    if not math.isfinite(temp_c):
        raise ValueError("CPU temperature is not finite")
    value = max(0, min(99, round(temp_c)))
    report = bytearray(REPORT_LENGTH)
    report[:3] = b"\x07\xff\xff"
    report[4] = value // 10
    report[5] = value % 10
    report[7] = 0  # Celsius
    return bytes(report)


def read_cpu_temperature() -> tuple[float, str]:
    """Read Intel core average or the AMD die/control temperature."""
    intel_samples = []
    amd_samples = {}
    for hwmon in sorted(SYS_HWMON.glob("hwmon*")):
        try:
            name = (hwmon / "name").read_text().strip()
        except OSError:
            continue
        if name not in ("coretemp", "k10temp"):
            continue
        try:
            for label_file in hwmon.glob("temp*_label"):
                label = label_file.read_text().strip()
                if name == "coretemp" and not (label.startswith("Core ") and label[5:].isdigit()):
                    continue
                if name == "k10temp" and label not in ("Tdie", "Tctl"):
                    continue
                input_file = label_file.with_name(label_file.name.replace("_label", "_input"))
                value = int(input_file.read_text().strip())
                if name == "coretemp":
                    intel_samples.append(value)
                else:
                    amd_samples.setdefault(label, value)
        except (OSError, ValueError) as error:
            raise RuntimeError(f"Could not read CPU temperature sensor: {error}") from error
    if intel_samples:
        return sum(intel_samples) / (1000.0 * len(intel_samples)), "Intel core average"
    for label in ("Tdie", "Tctl"):
        if label in amd_samples:
            return amd_samples[label] / 1000.0, f"AMD {label}"
    raise RuntimeError("No supported CPU temperature sensor found (coretemp Core N or k10temp Tdie/Tctl)")


def find_displays() -> list[Path]:
    """Return hidraw nodes matching both the USB identity and A62 report layout."""
    matches = []
    for entry in sorted(SYS_HIDRAW.glob("hidraw*")):
        try:
            hid_device = (entry / "device").resolve()
            descriptor = (hid_device / "report_descriptor").read_bytes()
            if FEATURE_DESCRIPTOR not in descriptor:
                continue
            interface = next(p for p in hid_device.parents if (p / "bInterfaceNumber").exists())
            usb_device = next(p for p in interface.parents if (p / "idVendor").exists())
            if (interface / "bInterfaceNumber").read_text().strip().lower() != INTERFACE:
                continue
            if (usb_device / "idVendor").read_text().strip().lower() != VID:
                continue
            if (usb_device / "idProduct").read_text().strip().lower() != PID:
                continue
            matches.append(Path("/dev") / entry.name)
        except (OSError, StopIteration):
            continue
    return matches


def unique_display() -> Path:
    matches = find_displays()
    if not matches:
        raise RuntimeError("Ocypus A62 HID interface was not found")
    if len(matches) > 1:
        raise RuntimeError(f"Multiple matching displays: {', '.join(map(str, matches))}")
    return matches[0]


def send_report(fd: int, report: bytes) -> None:
    # Linux hidraw.h: HIDIOCSFEATURE(len) = _IOC(_IOC_READ|_IOC_WRITE, 'H', 0x06, len)
    request = (3 << 30) | (len(report) << 16) | (ord("H") << 8) | 0x06
    result = fcntl.ioctl(fd, request, bytearray(report), True)
    if result != len(report):
        raise OSError(f"Feature report wrote {result} bytes, expected {len(report)}")


def show_once() -> None:
    temperature, source = read_cpu_temperature()
    display = unique_display()
    report = build_report(temperature)
    with os.fdopen(os.open(display, os.O_RDWR | os.O_CLOEXEC), "rb+", buffering=0) as device:
        send_report(device.fileno(), report)
    shown = max(0, min(99, round(temperature)))
    print(f"{display}: {shown:02d}°C ({source}: {temperature:.1f}°C)")


def watch(interval: float) -> None:
    stop = False

    def on_signal(_signum, _frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    last_report = None
    last_write = 0.0
    last_error = None
    while not stop:
        try:
            temperature, _source = read_cpu_temperature()
            report = build_report(temperature)
            if report != last_report or time.monotonic() - last_write >= 2.0:
                display = unique_display()
                with os.fdopen(os.open(display, os.O_RDWR | os.O_CLOEXEC), "rb+", buffering=0) as device:
                    send_report(device.fileno(), report)
                last_report = report
                last_write = time.monotonic()
                if last_error is not None:
                    print("Display connection restored", file=sys.stderr, flush=True)
                last_error = None
        except (OSError, RuntimeError, ValueError) as error:
            message = str(error)
            if message != last_error:
                print(message, file=sys.stderr, flush=True)
            last_error = message
            last_report = None
        if not stop:
            time.sleep(interval)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="show the USB device and CPU sensor without writing")
    subparsers.add_parser("once", help="send one Celsius temperature update")
    watch_parser = subparsers.add_parser("watch", help="update the display continuously")
    watch_parser.add_argument("--interval", type=float, default=1.0, help="seconds between sensor reads")
    args = parser.parse_args()
    try:
        if args.command == "status":
            temperature, source = read_cpu_temperature()
            display = unique_display()
            print(f"Display: {display}")
            print(f"CPU temperature ({source}): {temperature:.1f}°C")
            print(f"Report: {build_report(temperature).hex(' ')}")
        elif args.command == "once":
            show_once()
        else:
            if not math.isfinite(args.interval) or args.interval < 0.1:
                parser.error("--interval must be at least 0.1 seconds")
            watch(args.interval)
    except (OSError, RuntimeError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
