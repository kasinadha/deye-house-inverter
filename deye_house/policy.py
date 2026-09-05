"""Fixed 60% SOC floor / zero-export policy for the house hybrid inverter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SOC_FLOOR = 60
TOU_POWER_W = 6000
TOU_TIMES = ("00:00", "04:00", "08:00", "12:00", "16:00", "20:00")
TOU_DAYS = (
    "MONDAY",
    "TUESDAY",
    "WEDNESDAY",
    "THURSDAY",
    "FRIDAY",
    "SATURDAY",
    "SUNDAY",
)
WORK_MODE = "ZERO_EXPORT_TO_LOAD"
ENERGY_PATTERN = "LOAD_FIRST"


def tou_slots(enable_grid_charge: bool = True) -> list[dict[str, Any]]:
    return [
        {
            "enableGeneration": True,
            "enableGridCharge": enable_grid_charge,
            "power": TOU_POWER_W,
            "soc": SOC_FLOOR,
            "time": t,
        }
        for t in TOU_TIMES
    ]


def apply_orders(device_sn: str) -> list[tuple[str, str, dict[str, Any]]]:
    """Named (label, path, body) writes, one at a time."""
    return [
        (
            "workMode ZERO_EXPORT_TO_LOAD",
            "/order/sys/workMode/update",
            {"deviceSn": device_sn, "workMode": WORK_MODE},
        ),
        (
            "energyPattern LOAD_FIRST",
            "/order/sys/energyPattern/update",
            {"deviceSn": device_sn, "energyPattern": ENERGY_PATTERN},
        ),
        (
            "GRID_CHARGE on",
            "/order/battery/modeControl",
            {
                "deviceSn": device_sn,
                "batteryModeType": "GRID_CHARGE",
                "action": "on",
            },
        ),
        (
            "BATT_LOW=60",
            "/order/battery/parameter/update",
            {"deviceSn": device_sn, "paramterType": "BATT_LOW", "value": SOC_FLOOR},
        ),
        (
            "TOU slots SOC=60",
            "/order/sys/tou/update",
            {"deviceSn": device_sn, "timeUseSettingItems": tou_slots(True)},
        ),
        (
            "TOU on every day",
            "/order/sys/tou/switch",
            {"deviceSn": device_sn, "action": "on", "days": list(TOU_DAYS)},
        ),
        (
            "ZERO_EXPORT_POWER=0",
            "/order/sys/power/update",
            {"deviceSn": device_sn, "powerType": "ZERO_EXPORT_POWER", "value": 0},
        ),
        (
            "MAX_SELL_POWER=0",
            "/order/sys/power/update",
            {"deviceSn": device_sn, "powerType": "MAX_SELL_POWER", "value": 0},
        ),
        (
            "solarSell off",
            "/order/sys/solarSell/control",
            {"deviceSn": device_sn, "action": "off"},
        ),
    ]


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value).split()[0]))
    except (TypeError, ValueError):
        return None


def _as_boolish_on(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return text in {"on", "true", "1", "yes"}


def normalize_tou_time(value: Any) -> str:
    raw = str(value).strip().replace(":", "")
    if len(raw) == 3:
        raw = f"0{raw}"
    if len(raw) == 4 and raw.isdigit():
        return f"{raw[:2]}:{raw[2:]}"
    return str(value).strip()


@dataclass(frozen=True)
class Check:
    name: str
    expected: Any
    actual: Any
    ok: bool


def verify_config(
    system: dict[str, Any],
    tou: dict[str, Any],
    battery: dict[str, Any],
) -> list[Check]:
    items = tou.get("timeUseSettingItems") or tou.get("touSettingItems") or []
    checks = [
        Check(
            "systemWorkMode",
            WORK_MODE,
            system.get("systemWorkMode") or system.get("workMode"),
            (system.get("systemWorkMode") or system.get("workMode")) == WORK_MODE,
        ),
        Check(
            "energyPattern",
            ENERGY_PATTERN,
            system.get("energyPattern"),
            system.get("energyPattern") == ENERGY_PATTERN,
        ),
        Check(
            "maxSellPower",
            0,
            _as_int(system.get("maxSellPower")),
            _as_int(system.get("maxSellPower")) == 0,
        ),
        Check(
            "zeroExportPower",
            0,
            _as_int(system.get("zeroExportPower")),
            _as_int(system.get("zeroExportPower")) == 0,
        ),
        Check(
            "touAction",
            "on",
            tou.get("touAction"),
            _as_boolish_on(tou.get("touAction")),
        ),
        Check("touSlotCount", 6, len(items), len(items) == 6),
        Check(
            "battLowCapacity",
            SOC_FLOOR,
            _as_int(battery.get("battLowCapacity")),
            _as_int(battery.get("battLowCapacity")) == SOC_FLOOR,
        ),
    ]

    expected_times = list(TOU_TIMES)
    actual_times = [normalize_tou_time(slot.get("time")) for slot in items]
    checks.append(Check("touTimes", expected_times, actual_times, actual_times == expected_times))

    for i, slot in enumerate(items):
        prefix = f"slot{i}"
        checks.append(
            Check(
                f"{prefix}.soc",
                SOC_FLOOR,
                _as_int(slot.get("soc")),
                _as_int(slot.get("soc")) == SOC_FLOOR,
            )
        )
        checks.append(
            Check(
                f"{prefix}.enableGridCharge",
                True,
                slot.get("enableGridCharge"),
                bool(slot.get("enableGridCharge")) is True,
            )
        )
        checks.append(
            Check(
                f"{prefix}.enableGeneration",
                True,
                slot.get("enableGeneration"),
                bool(slot.get("enableGeneration")) is True,
            )
        )
        checks.append(
            Check(
                f"{prefix}.power",
                TOU_POWER_W,
                _as_int(slot.get("power")),
                _as_int(slot.get("power")) == TOU_POWER_W,
            )
        )
    return checks


def policy_state(soc: float | None) -> str:
    if soc is None:
        return "unknown"
    if soc > SOC_FLOOR:
        return "above_floor"
    if soc < SOC_FLOOR:
        return "below_floor"
    return "at_floor"
