import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from deye_house.policy import (
    BATT_LOW,
    SITE_TZ,
    SOC_FLOOR_DAY,
    SOC_FLOOR_NIGHT,
    active_soc_floor,
    apply_orders,
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
        self.assertEqual(active_soc_floor(evening), 40)
        self.assertEqual(SOC_FLOOR_DAY, 40)
        self.assertEqual(SOC_FLOOR_NIGHT, 40)
        self.assertEqual(BATT_LOW, 40)
        self.assertLessEqual(SOC_FLOOR_NIGHT, SOC_FLOOR_DAY)

    def test_policy_state(self) -> None:
        day = datetime(2026, 9, 5, 12, 0, tzinfo=SITE_TZ)
        night = datetime(2026, 9, 5, 20, 0, tzinfo=SITE_TZ)
        self.assertIn("above_floor", policy_state(99, day))
        self.assertIn("40%", policy_state(50, day))
        self.assertIn("day", policy_state(50, day))
        self.assertIn("below_floor", policy_state(39, day))
        # Typical evening SOC (~70–80%) must be above the night floor so the
        # battery is allowed to cover overnight house load.
        self.assertIn("above_floor", policy_state(77, night))
        self.assertIn("night", policy_state(77, night))
        self.assertIn("above_floor", policy_state(50, night))
        self.assertIn("at_floor", policy_state(40, night))
        self.assertIn("below_floor", policy_state(39, night))

    def test_verify_matches_target(self) -> None:
        system = {
            "systemWorkMode": "ZERO_EXPORT_TO_LOAD",
            "energyPattern": "LOAD_FIRST",
            "maxSellPower": 0,
            "zeroExportPower": 0,
        }
        tou = {"touAction": "on", "timeUseSettingItems": tou_slots()}
        tou["timeUseSettingItems"][2]["time"] = "0900"
        battery = {"battLowCapacity": 40, "battShutDownCapacity": 20}
        checks = verify_config(system, tou, battery)
        self.assertTrue(all(c.ok for c in checks), checks)
        slots = tou_slots()
        self.assertEqual([s["soc"] for s in slots], [40, 40, 40, 40, 40, 40])
        self.assertEqual([s["time"] for s in slots], ["00:00", "04:00", "09:00", "12:00", "16:00", "20:00"])
        self.assertTrue(all(s["enableGridCharge"] is False for s in slots))
        self.assertTrue(all(s["enableGeneration"] is True for s in slots))
        self.assertTrue(all(s["power"] == 6000 for s in slots))

    def test_verify_detects_old_night_70_schedule(self) -> None:
        """Night SOC=70 locks discharge; house then imports overnight."""
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
                    "soc": soc,
                    "time": t,
                }
                for t, soc in (
                    ("00:00", 70),
                    ("04:00", 70),
                    ("09:00", 40),
                    ("12:00", 40),
                    ("16:00", 70),
                    ("20:00", 70),
                )
            ],
        }
        battery = {"battLowCapacity": 40}
        checks = verify_config(system, tou, battery)
        self.assertFalse(all(c.ok for c in checks))
        failed = {c.name for c in checks if not c.ok}
        self.assertTrue(any(name.endswith(".soc") for name in failed), failed)

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

    def test_apply_orders_keep_known_paths_and_guards(self) -> None:
        orders = apply_orders("SN123")
        paths = [path for _, path, _ in orders]
        self.assertEqual(
            paths,
            [
                "/order/sys/workMode/update",
                "/order/sys/energyPattern/update",
                "/order/battery/modeControl",
                "/order/battery/parameter/update",
                "/order/sys/tou/update",
                "/order/sys/tou/switch",
                "/order/sys/power/update",
                "/order/sys/power/update",
                "/order/sys/solarSell/control",
            ],
        )
        by_path = {path: body for _, path, body in orders}
        self.assertEqual(by_path["/order/battery/modeControl"]["action"], "off")
        self.assertEqual(by_path["/order/battery/modeControl"]["batteryModeType"], "GRID_CHARGE")
        self.assertEqual(by_path["/order/battery/parameter/update"]["value"], 40)
        self.assertEqual(by_path["/order/sys/workMode/update"]["workMode"], "ZERO_EXPORT_TO_LOAD")
        self.assertEqual(by_path["/order/sys/energyPattern/update"]["energyPattern"], "LOAD_FIRST")
        power_orders = [body for _, path, body in orders if path == "/order/sys/power/update"]
        self.assertEqual({body["powerType"] for body in power_orders}, {"ZERO_EXPORT_POWER", "MAX_SELL_POWER"})
        self.assertTrue(all(body["value"] == 0 for body in power_orders))
        tou_items = by_path["/order/sys/tou/update"]["timeUseSettingItems"]
        self.assertEqual(len(tou_items), 6)
        self.assertEqual([item["soc"] for item in tou_items], [40, 40, 40, 40, 40, 40])
        self.assertTrue(all(item["enableGridCharge"] is False for item in tou_items))

    def test_verify_detects_slot_grid_charge_enabled(self) -> None:
        """Grid Charge on a slot can leave a full pack idle while the house imports."""
        system = {
            "systemWorkMode": "ZERO_EXPORT_TO_LOAD",
            "energyPattern": "LOAD_FIRST",
            "maxSellPower": 0,
            "zeroExportPower": 0,
        }
        tou = {"touAction": "on", "timeUseSettingItems": tou_slots()}
        tou["timeUseSettingItems"][3]["enableGridCharge"] = True  # 12:00–16:00
        battery = {"battLowCapacity": 40}
        checks = verify_config(system, tou, battery)
        self.assertFalse(all(c.ok for c in checks))
        failed = {c.name: c for c in checks if not c.ok}
        self.assertIn("slot3.enableGridCharge", failed)
        self.assertEqual(failed["slot3.enableGridCharge"].expected, False)


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
