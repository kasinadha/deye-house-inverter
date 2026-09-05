"""Parse /device/latest dataList into the policy fields."""

from __future__ import annotations

from typing import Any

KEYS = {
    "pvPower": "TotalDCInputPower",
    "loadPower": "TotalConsumptionPower",
    "upsLoadPower": "UPSLoadPower",
    "gridPower": "TotalGridPower",
    "batterySoc": "SOC",
    "batteryPower": "BatteryPower",
    "dailyImport": "DailyEnergyPurchased",
    "dailyExport": "DailyEnergySold",
}


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).split()[0])
    except (TypeError, ValueError):
        return None


def data_map(latest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    devices = latest.get("deviceDataList") or latest.get("devices") or []
    if not devices:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for item in devices[0].get("dataList") or []:
        key = item.get("key")
        if key:
            out[str(key)] = item
    return out


def parse_latest(latest: dict[str, Any]) -> dict[str, Any]:
    mapped = data_map(latest)
    parsed: dict[str, Any] = {}
    for alias, key in KEYS.items():
        item = mapped.get(key) or {}
        parsed[alias] = _num(item.get("value"))
        parsed[f"{alias}Unit"] = item.get("unit")
    return parsed
