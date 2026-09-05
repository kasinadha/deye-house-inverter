import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from deye_house.policy import (
    SITE_TZ,
    active_soc_floor,
    is_day_window,
    normalize_tou_time,
    policy_state,
    tou_slots,
    verify_config,
)
from deye_house.telemetry import parse_latest


class PolicyTests(unittest.TestCase):
    def test_tou_times_normalize(self) -> None:
        self.assertEqual(normalize_tou_time("0000"), "00:00")
        self.assertEqual(normalize_tou_time("04:00"), "04:00")
        self.assertEqual(normalize_tou_time(1600), "16:00")
        self.assertEqual(normalize_tou_time("0900"), "09:00")

    def test_day_window_and_floor(self) -> None:
        day = datetime(2026, 9, 5, 12, 0, tzinfo=SITE_TZ)
        just_before = datetime(2026, 9, 5, 8, 59, tzinfo=SITE_TZ)
        at_start = datetime(2026, 9, 5, 9, 0, tzinfo=SITE_TZ)
        at_end = datetime(2026, 9, 5, 16, 0, tzinfo=SITE_TZ)
        evening = datetime(2026, 9, 5, 16, 1, tzinfo=SITE_TZ)
        utc_noon_ist = datetime(2026, 9, 5, 6, 30, tzinfo=ZoneInfo("UTC"))  # 12:00 IST

        self.assertTrue(is_day_window(day))
        self.assertTrue(is_day_window(at_start))
        self.assertTrue(is_day_window(utc_noon_ist))
        self.assertFalse(is_day_window(just_before))
        self.assertFalse(is_day_window(at_end))
        self.assertFalse(is_day_window(evening))
        self.assertEqual(active_soc_floor(day), 40)
        self.assertEqual(active_soc_floor(evening), 60)

    def test_policy_state(self) -> None:
        day = datetime(2026, 9, 5, 12, 0, tzinfo=SITE_TZ)
        night = datetime(2026, 9, 5, 20, 0, tzinfo=SITE_TZ)
        self.assertIn("above_floor", policy_state(99, day))
        self.assertIn("40%", policy_state(50, day))
        self.assertIn("below_floor", policy_state(39, day))
        self.assertIn("below_floor", policy_state(50, night))
        self.assertIn("at_floor", policy_state(60, night))

    def test_verify_matches_target(self) -> None:
        system = {
            "systemWorkMode": "ZERO_EXPORT_TO_LOAD",
            "energyPattern": "LOAD_FIRST",
            "maxSellPower": 0,
            "zeroExportPower": 0,
        }
        tou = {"touAction": "on", "timeUseSettingItems": tou_slots(True)}
        tou["timeUseSettingItems"][2]["time"] = "0900"
        battery = {"battLowCapacity": 40, "battShutDownCapacity": 20}
        checks = verify_config(system, tou, battery)
        self.assertTrue(all(c.ok for c in checks), checks)
        slots = tou_slots()
        self.assertEqual([s["soc"] for s in slots], [60, 60, 40, 40, 60, 60])
        self.assertEqual([s["time"] for s in slots], ["00:00", "04:00", "09:00", "12:00", "16:00", "20:00"])

    def test_verify_detects_old_all_60_schedule(self) -> None:
        system = {
            "systemWorkMode": "ZERO_EXPORT_TO_LOAD",
            "energyPattern": "LOAD_FIRST",
            "maxSellPower": 0,
            "zeroExportPower": 0,
        }
        tou = {
            "touAction": "on",
            "timeUseSettingItems": [
                {
                    "enableGeneration": True,
                    "enableGridCharge": True,
                    "power": 6000,
                    "soc": 60,
                    "time": t,
                }
                for t in ("00:00", "04:00", "08:00", "12:00", "16:00", "20:00")
            ],
        }
        battery = {"battLowCapacity": 60}
        checks = verify_config(system, tou, battery)
        self.assertFalse(all(c.ok for c in checks))


class TelemetryTests(unittest.TestCase):
    def test_parse_latest(self) -> None:
        payload = {
            "deviceDataList": [
                {
                    "dataList": [
                        {"key": "TotalDCInputPower", "value": "981", "unit": "W"},
                        {"key": "TotalConsumptionPower", "value": "2079", "unit": "W"},
                        {"key": "SOC", "value": "99", "unit": "%"},
                        {"key": "TotalGridPower", "value": "103", "unit": "W"},
                        {"key": "BatteryPower", "value": "1040", "unit": "W"},
                    ]
                }
            ]
        }
        parsed = parse_latest(payload)
        self.assertEqual(parsed["pvPower"], 981)
        self.assertEqual(parsed["loadPower"], 2079)
        self.assertEqual(parsed["batterySoc"], 99)
        self.assertEqual(parsed["gridPower"], 103)
        self.assertEqual(parsed["batteryPower"], 1040)


if __name__ == "__main__":
    unittest.main()
