import unittest

from deye_house.policy import normalize_tou_time, policy_state, tou_slots, verify_config
from deye_house.telemetry import parse_latest


class PolicyTests(unittest.TestCase):
    def test_tou_times_normalize(self) -> None:
        self.assertEqual(normalize_tou_time("0000"), "00:00")
        self.assertEqual(normalize_tou_time("04:00"), "04:00")
        self.assertEqual(normalize_tou_time(1600), "16:00")

    def test_policy_state(self) -> None:
        self.assertEqual(policy_state(99), "above_floor")
        self.assertEqual(policy_state(60), "at_floor")
        self.assertEqual(policy_state(59.4), "below_floor")

    def test_verify_matches_target(self) -> None:
        system = {
            "systemWorkMode": "ZERO_EXPORT_TO_LOAD",
            "energyPattern": "LOAD_FIRST",
            "maxSellPower": 0,
            "zeroExportPower": 0,
        }
        tou = {"touAction": "on", "timeUseSettingItems": tou_slots(True)}
        tou["timeUseSettingItems"][1]["time"] = "0400"
        battery = {"battLowCapacity": 60, "battShutDownCapacity": 20}
        checks = verify_config(system, tou, battery)
        self.assertTrue(all(c.ok for c in checks), checks)

    def test_verify_detects_old_floor(self) -> None:
        system = {
            "systemWorkMode": "ZERO_EXPORT_TO_CT",
            "energyPattern": "BATTERY_FIRST",
            "maxSellPower": 20,
            "zeroExportPower": 20,
        }
        tou = {"touAction": "off", "timeUseSettingItems": []}
        battery = {"battLowCapacity": 40}
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
