"""CLI: status / apply / verify."""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Any

from deye_house.client import DeyeClient, DeyeError, discover_inverter, env_file_path
from deye_house.policy import active_soc_floor, apply_orders, policy_state, verify_config
from deye_house.telemetry import parse_latest


def _print(msg: str) -> None:
    print(msg, flush=True)


def _connect(args: argparse.Namespace) -> tuple[DeyeClient, dict[str, Any]]:
    path = env_file_path(getattr(args, "villa", None), getattr(args, "env", None))
    _print(f"Credentials file: {path} (not uploaded to git)")
    client = DeyeClient.from_env(path)
    login = client.login()
    _print(f"Logged in uid={login.get('uid')} (token hidden)")
    preferred = os.environ.get("DEYE_DEVICE_SN", "").strip() or None
    device = discover_inverter(client, preferred)
    _print(
        f"Inverter {device['deviceSn']}  station={device.get('stationName') or '-'} "
        f"id={device.get('stationId') or '-'}"
    )
    return client, device


def _snapshot(client: DeyeClient, device: dict[str, Any]) -> dict[str, Any]:
    sn = device["deviceSn"]
    latest = client.device_latest(sn)
    telemetry = parse_latest(latest)
    system = client.config_system(sn)
    tou = client.config_tou(sn)
    battery = client.config_battery(sn)
    station = None
    if device.get("stationId") is not None:
        try:
            station = client.station_latest(int(device["stationId"]))
        except (DeyeError, TypeError, ValueError):
            station = None
    checks = verify_config(system, tou, battery)
    return {
        "device": device,
        "telemetry": telemetry,
        "system": system,
        "tou": tou,
        "battery": battery,
        "station": station,
        "checks": checks,
        "policyState": policy_state(telemetry.get("batterySoc")),
    }


def _print_status(snap: dict[str, Any]) -> None:
    t = snap["telemetry"]
    _print("")
    _print("Live telemetry (/device/latest)")
    _print(f"  pvPower       {t.get('pvPower')} {t.get('pvPowerUnit') or 'W'}")
    _print(f"  loadPower     {t.get('loadPower')} {t.get('loadPowerUnit') or 'W'}")
    _print(f"  batterySoc    {t.get('batterySoc')} %")
    _print(f"  batteryPower  {t.get('batteryPower')} {t.get('batteryPowerUnit') or 'W'}  (+discharge / -charge)")
    _print(f"  gridPower     {t.get('gridPower')} {t.get('gridPowerUnit') or 'W'}  (+import)")
    _print(f"  dailyImport   {t.get('dailyImport')} {t.get('dailyImportUnit') or 'kWh'}")
    _print(f"  policy        {snap['policyState']}")
    _print("")
    _print("Config vs daytime 40% / night 60% target")
    failed = 0
    for check in snap["checks"]:
        mark = "ok" if check.ok else "FAIL"
        if not check.ok:
            failed += 1
        _print(f"  [{mark}] {check.name}: expected {check.expected!r} got {check.actual!r}")
    _print("")
    if failed:
        _print(f"{failed} check(s) not matching target.")
    else:
        _print("Config matches the daytime 40% / night 60% SOC policy.")

    soc = t.get("batterySoc")
    grid = t.get("gridPower") or 0
    batt = t.get("batteryPower") or 0
    floor = active_soc_floor()
    if soc is not None and soc > floor and grid > 300 and batt <= 50:
        _print(
            f"Warning: SOC is above the active {floor}% floor but grid import is large "
            "and the battery is not discharging. Re-run apply."
        )


def cmd_status(args: argparse.Namespace) -> int:
    client, device = _connect(args)
    snap = _snapshot(client, device)
    _print_status(snap)
    return 0 if all(c.ok for c in snap["checks"]) else 1


def _reread_until_ok(client: DeyeClient, device: dict[str, Any], tries: int = 6) -> dict[str, Any]:
    snap = _snapshot(client, device)
    for i in range(tries - 1):
        if all(c.ok for c in snap["checks"]):
            return snap
        _print(f"Config still lagging ({i + 1}/{tries}); waiting 8s...")
        time.sleep(8)
        snap = _snapshot(client, device)
    return snap


def cmd_apply(args: argparse.Namespace) -> int:
    client, device = _connect(args)
    sn = device["deviceSn"]
    before = _snapshot(client, device)
    _print("Before:")
    _print_status(before)
    if args.dry_run:
        _print("Dry run — no orders sent.")
        return 0
    _print("Applying orders one at a time...")
    for name, path, body in apply_orders(sn):
        _print(f"\n=== {name} ===")
        result = client.send_order(name, path, body)
        _print(f"  orderId={result.order_id} status={result.status} error={result.error}")
        if result.status not in {666, None}:
            _print(f"  order did not succeed (status {result.status})")
            return 2
        time.sleep(1)
    snap = _reread_until_ok(client, device)
    _print("\nAfter:")
    _print_status(snap)
    return 0 if all(c.ok for c in snap["checks"]) else 1


def cmd_verify(args: argparse.Namespace) -> int:
    client, device = _connect(args)
    snap = _snapshot(client, device)
    _print_status(snap)
    if not all(c.ok for c in snap["checks"]):
        _print("verify failed")
        return 1
    _print("verify passed")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m deye_house",
        description="Apply a 40%% daytime / 60%% night SOC floor and zero-export policy via DeyeCloud India OpenAPI.",
    )
    parser.add_argument(
        "--villa",
        metavar="NAME",
        help="Load gitignored .env.NAME (example: --villa villa431). Do not commit this file.",
    )
    parser.add_argument(
        "--env",
        metavar="PATH",
        help="Credential file path (default .env). Ignored if --villa is set.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="Print live telemetry and config; no writes")
    apply_p = sub.add_parser("apply", help="Write the SOC policy, then verify")
    apply_p.add_argument("--dry-run", action="store_true", help="Show current state only")
    sub.add_parser("verify", help="Exit non-zero if config != target")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "status":
            return cmd_status(args)
        if args.command == "apply":
            return cmd_apply(args)
        if args.command == "verify":
            return cmd_verify(args)
        parser.error("unknown command")
        return 2
    except DeyeError as exc:
        _print(f"error: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
