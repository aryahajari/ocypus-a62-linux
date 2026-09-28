import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import ocypus_a62


class ReportTests(unittest.TestCase):
    def test_celsius_report_layout(self):
        report = ocypus_a62.build_report(42.6)
        self.assertEqual(len(report), 64)
        self.assertEqual(report[:8], bytes.fromhex("07 ff ff 00 04 03 00 00"))
        self.assertEqual(report[8:], bytes(56))

    def test_display_range(self):
        self.assertEqual(ocypus_a62.build_report(-5)[4:6], b"\x00\x00")
        self.assertEqual(ocypus_a62.build_report(120)[4:6], b"\x09\x09")

    def test_nonfinite_temperature_is_rejected(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ocypus_a62.build_report(value)


class SensorTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.hwmon_root = Path(self.directory.name)
        self.patch = patch.object(ocypus_a62, "SYS_HWMON", self.hwmon_root)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def add_sensor(self, number, name, readings):
        hwmon = self.hwmon_root / f"hwmon{number}"
        hwmon.mkdir()
        (hwmon / "name").write_text(name)
        for index, (label, millidegrees) in enumerate(readings, start=1):
            (hwmon / f"temp{index}_label").write_text(label)
            (hwmon / f"temp{index}_input").write_text(str(millidegrees))

    def test_intel_averages_cores_only(self):
        self.add_sensor(0, "coretemp", [("Package id 0", 70000), ("Core 0", 40000), ("Core 1", 46000)])
        self.assertEqual(ocypus_a62.read_cpu_temperature(), (43.0, "Intel core average"))

    def test_amd_prefers_tdie(self):
        self.add_sensor(0, "k10temp", [("Tctl", 57000), ("Tdie", 50000)])
        self.assertEqual(ocypus_a62.read_cpu_temperature(), (50.0, "AMD Tdie"))

    def test_amd_falls_back_to_tctl(self):
        self.add_sensor(0, "k10temp", [("Tctl", 55000)])
        self.assertEqual(ocypus_a62.read_cpu_temperature(), (55.0, "AMD Tctl"))

    def test_missing_supported_sensor_is_reported(self):
        self.add_sensor(0, "acpitz", [("temp1", 35000)])
        with self.assertRaisesRegex(RuntimeError, "No supported CPU temperature sensor"):
            ocypus_a62.read_cpu_temperature()

    def test_incomplete_sensor_is_reported(self):
        self.add_sensor(0, "coretemp", [("Core 0", 40000)])
        (self.hwmon_root / "hwmon0" / "temp1_input").unlink()
        with self.assertRaisesRegex(RuntimeError, "Could not read CPU temperature sensor"):
            ocypus_a62.read_cpu_temperature()


if __name__ == "__main__":
    unittest.main()
