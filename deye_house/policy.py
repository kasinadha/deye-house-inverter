"""SOC floor / zero-export policy for the house hybrid inverter.

Goal: minimize daily grid import. PV covers whatever load it can; the battery
covers the rest down to a 40% floor; grid is last.

Deye TOU ``enableGridCharge`` is permission to use the *grid as a source* in
that slot. With it on, a full battery can sit idle while the house imports
(confirmed 2026-09-19 15:28 IST: PV 3.36 kW, UPS load 4.60 kW, grid 1.36 kW,
battery 99% / 31 W). Slots keep Grid Charge **off** so SOC=40% is a discharge
floor, not a "use grid" flag. Global GRID_CHARGE master stays off too.

A high night SOC (70%) also forbids discharging below 70%. Both traps cause
overnight grid-for-load. Day window 09:00–16:00 is for status labels only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

SITE_TZ = ZoneInfo("Asia/Kolkata")
# Same emergency floor day and night. Night must not sit above day, or 09:00
# would grid-charge the gap. 40% matches the established daytime safety line
# and stays above a typical ~20% shutdown.
SOC_FLOOR_NIGHT = 40
SOC_FLOOR_DAY = 40
DAY_START = time(9, 0)
DAY_END = time(16, 0)
TOU_POWER_W = 6000
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

# Each slot lasts until the next. SOC is the discharge floor. Grid Charge off
# so PV+battery supply the house; grid covers load only after SOC hits 40%.
# Do not leave the global GRID_CHARGE master on — that filled past the TOU
# target overnight (~90%). Do not tick slot Grid Charge either — that is how
# a 99% pack still imports while the sun is up.
TOU_SLOTS = (
    {"time": "00:00", "soc": SOC_FLOOR_NIGHT, "enableGridCharge": False},
    {"time": "04:00", "soc": SOC_FLOOR_NIGHT, "enableGridCharge": False},
    {"time": "09:00", "soc": SOC_FLOOR_DAY, "enableGridCharge": False},
    {"time": "12:00", "soc": SOC_FLOOR_DAY, "enableGridCharge": False},
    {"time": "16:00", "soc": SOC_FLOOR_NIGHT, "enableGridCharge": False},
    {"time": "20:00", "soc": SOC_FLOOR_NIGHT, "enableGridCharge": False},
)
TOU_TIMES = tuple(slot["time"] for slot in TOU_SLOTS)

# Hard low-SOC must match the lowest TOU floor or discharge stops early.
BATT_LOW = min(SOC_FLOOR_DAY, SOC_FLOOR_NIGHT)


def is_day_window(when: datetime | None = None) -> bool:
    if when is None:
        now = datetime.now(SITE_TZ)
    elif when.tzinfo is None:
        now = when.replace(tzinfo=SITE_TZ)
    else:
        now = when.astimezone(SITE_TZ)
    clock = now.time().replace(tzinfo=None)
    return DAY_START <= clock < DAY_END


def active_soc_floor(when: datetime | None = None) -> int:
    return SOC_FLOOR_DAY if is_day_window(when) else SOC_FLOOR_NIGHT


def tou_slots(enable_grid_charge: bool | None = None) -> list[dict[str, Any]]:
    return [
        {
            "enableGeneration": True,
            "enableGridCharge": (
                enable_grid_charge
                if enable_grid_charge is not None
                else bool(slot.get("enableGridCharge", False))
            ),
            "power": TOU_POWER_W,
            "soc": slot["soc"],
            "time": slot["time"],
        }
        for slot in TOU_SLOTS
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
            "GRID_CHARGE off (do not grid-charge the pack)",
            "/order/battery/modeControl",
            {
                "deviceSn": device_sn,
                "batteryModeType": "GRID_CHARGE",
                "action": "off",
            },
        ),
        (
            f"BATT_LOW={BATT_LOW}",
            "/order/battery/parameter/update",
            {"deviceSn": device_sn, "paramterType": "BATT_LOW", "value": BATT_LOW},
        ),
        (
            f"TOU slots {SOC_FLOOR_DAY}%/{SOC_FLOOR_NIGHT}% floor, grid-charge off",
            "/order/sys/tou/update",
            {"deviceSn": device_sn, "timeUseSettingItems": tou_slots()},
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
            BATT_LOW,
            _as_int(battery.get("battLowCapacity")),
            _as_int(battery.get("battLowCapacity")) == BATT_LOW,
        ),
    ]

    expected_times = list(TOU_TIMES)
    actual_times = [normalize_tou_time(slot.get("time")) for slot in items]
    checks.append(Check("touTimes", expected_times, actual_times, actual_times == expected_times))

    for i, slot in enumerate(items):
        prefix = f"slot{i}"
        expected_soc = TOU_SLOTS[i]["soc"] if i < len(TOU_SLOTS) else None
        checks.append(
            Check(
                f"{prefix}.soc",
                expected_soc,
                _as_int(slot.get("soc")),
                _as_int(slot.get("soc")) == expected_soc,
            )
        )
        expected_grid = (
            bool(TOU_SLOTS[i].get("enableGridCharge", False)) if i < len(TOU_SLOTS) else False
        )
        checks.append(
            Check(
                f"{prefix}.enableGridCharge",
                expected_grid,
                slot.get("enableGridCharge"),
                bool(slot.get("enableGridCharge")) is expected_grid,
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


def policy_state(soc: float | None, when: datetime | None = None) -> str:
    floor = active_soc_floor(when)
    window = "day" if is_day_window(when) else "night"
    if soc is None:
        return f"unknown ({window} floor {floor}%)"
    if soc > floor:
        return f"above_floor ({window} {floor}%)"
    if soc < floor:
        return f"below_floor ({window} {floor}%)"
    return f"at_floor ({window} {floor}%)"
