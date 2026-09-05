"""India DeyeCloud OpenAPI client (stdlib urllib only)."""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

INDIA_BASE_URL = "https://india-developer.deyecloud.com/v1.0"
CONCURRENT_CODE = "2104004"
SUCCESS_STATUSES = {666}
FAIL_STATUSES = {400, 500}


class DeyeError(RuntimeError):
    pass


def load_dotenv(path: str = ".env") -> None:
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            if key and key not in os.environ:
                os.environ[key] = value


def sha256_hex(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest().lower()


def _json_body(payload: dict[str, Any] | None) -> bytes | None:
    if payload is None:
        return None
    return json.dumps(payload).encode("utf-8")


@dataclass
class OrderResult:
    name: str
    path: str
    order_id: str | None
    status: int | None
    error: Any
    send: dict[str, Any]
    poll: dict[str, Any] | None


class DeyeClient:
    def __init__(
        self,
        app_id: str,
        app_secret: str,
        email: str,
        password: str,
        base_url: str = INDIA_BASE_URL,
        timeout: int = 45,
    ) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.email = email
        self.password = password
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.token: str | None = None

    @classmethod
    def from_env(cls) -> DeyeClient:
        load_dotenv()
        missing = [
            name
            for name in ("DEYE_APP_ID", "DEYE_APP_SECRET", "DEYE_EMAIL", "DEYE_PASSWORD")
            if not os.environ.get(name)
        ]
        if missing:
            raise DeyeError(
                "Missing env vars: " + ", ".join(missing) + ". Copy .env.example to .env."
            )
        return cls(
            app_id=os.environ["DEYE_APP_ID"].strip(),
            app_secret=os.environ["DEYE_APP_SECRET"].strip(),
            email=os.environ["DEYE_EMAIL"].strip(),
            password=os.environ["DEYE_PASSWORD"],
            base_url=os.environ.get("DEYE_BASE_URL", INDIA_BASE_URL).strip(),
        )

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        query: str = "",
        auth: bool = True,
        retries: int = 5,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}{query}"
        headers = {"Content-Type": "application/json"}
        if auth:
            if not self.token:
                raise DeyeError("Not authenticated")
            headers["Authorization"] = f"Bearer {self.token}"
        last_error: Exception | None = None
        for attempt in range(retries):
            req = urllib.request.Request(
                url,
                data=_json_body(body),
                headers=headers,
                method=method,
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read().decode("utf-8")
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as exc:
                payload = exc.read().decode("utf-8", errors="replace")[:2000]
                if exc.code in {403, 429} and attempt < retries - 1:
                    time.sleep(3 + attempt)
                    last_error = DeyeError(f"HTTP {exc.code} {path}: {payload}")
                    continue
                raise DeyeError(f"HTTP {exc.code} {path}: {payload}") from exc
            except urllib.error.URLError as exc:
                last_error = DeyeError(f"{path}: {exc}")
                time.sleep(2)
        raise last_error or DeyeError(f"{path}: request failed")

    def post(self, path: str, body: dict[str, Any] | None = None, query: str = "") -> dict[str, Any]:
        return self.request("POST", path, body if body is not None else {}, query=query)

    def get(self, path: str) -> dict[str, Any]:
        return self.request("GET", path, body=None)

    def login(self) -> dict[str, Any]:
        result = self.request(
            "POST",
            "/account/token",
            {
                "appSecret": self.app_secret,
                "email": self.email,
                "password": sha256_hex(self.password),
            },
            query=f"?appId={self.app_id}",
            auth=False,
        )
        token = result.get("accessToken")
        if not token:
            raise DeyeError(f"Login failed: {result.get('code')} {result.get('msg')}")
        self.token = str(token)
        return result

    def send_order(self, name: str, path: str, body: dict[str, Any]) -> OrderResult:
        send: dict[str, Any] = {}
        for attempt in range(12):
            send = self.post(path, body)
            if send.get("success") and send.get("orderId"):
                break
            if send.get("code") == CONCURRENT_CODE:
                time.sleep(4 + attempt)
                continue
            raise DeyeError(f"{name} rejected: {send.get('code')} {send.get('msg')}")
        order_id = send.get("orderId")
        if not order_id:
            raise DeyeError(f"{name} produced no orderId: {send}")
        poll = self.wait_order(str(order_id))
        return OrderResult(
            name=name,
            path=path,
            order_id=str(order_id),
            status=poll.get("status") if poll else None,
            error=poll.get("error") if poll else None,
            send=send,
            poll=poll,
        )

    def wait_order(self, order_id: str, attempts: int = 20) -> dict[str, Any]:
        last: dict[str, Any] = {}
        for _ in range(attempts):
            try:
                last = self.get(f"/order/{order_id}")
            except DeyeError:
                time.sleep(4)
                continue
            status = last.get("status")
            if status in SUCCESS_STATUSES or status in FAIL_STATUSES:
                return last
            time.sleep(3)
        return last

    def station_list(self) -> dict[str, Any]:
        return self.post("/station/list", {"page": 1, "size": 50})

    def station_list_with_device(self) -> dict[str, Any]:
        return self.post("/station/listWithDevice", {"page": 1, "size": 50})

    def station_latest(self, station_id: int) -> dict[str, Any]:
        return self.post("/station/latest", {"stationId": station_id})

    def device_latest(self, device_sn: str) -> dict[str, Any]:
        return self.post(
            "/device/latest",
            {"deviceList": [device_sn], "deviceType": "INVERTER"},
        )

    def config_system(self, device_sn: str) -> dict[str, Any]:
        return self.post("/config/system", {"deviceSn": device_sn})

    def config_tou(self, device_sn: str) -> dict[str, Any]:
        return self.post("/config/tou", {"deviceSn": device_sn})

    def config_battery(self, device_sn: str) -> dict[str, Any]:
        return self.post("/config/battery", {"deviceSn": device_sn})


def _walk_with_station(
    obj: Any,
    station_id: Any = None,
    station_name: Any = None,
):
    if isinstance(obj, dict):
        looks_like_station = any(
            key in obj for key in ("stationName", "stationId", "deviceListItems", "deviceList")
        )
        if looks_like_station:
            station_id = obj.get("stationId") or obj.get("id") or station_id
            station_name = obj.get("stationName") or obj.get("name") or station_name
        yield obj, station_id, station_name
        for value in obj.values():
            yield from _walk_with_station(value, station_id, station_name)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk_with_station(item, station_id, station_name)


def _device_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for node, station_id, station_name in _walk_with_station(payload):
        sn = node.get("deviceSn") or node.get("sn")
        dtype = str(node.get("deviceType") or node.get("type") or "").upper()
        if not sn:
            continue
        sn = str(sn)
        if sn in seen:
            continue
        if "COLLECTOR" in dtype or dtype == "BATTERY":
            continue
        if dtype and "INVERTER" not in dtype:
            continue
        seen.add(sn)
        rows.append(
            {
                "deviceSn": sn,
                "deviceType": dtype or "INVERTER",
                "stationId": node.get("stationId") or station_id,
                "stationName": node.get("stationName") or station_name,
                "productId": node.get("productId"),
            }
        )
    return rows


def discover_inverter(client: DeyeClient, preferred_sn: str | None = None) -> dict[str, Any]:
    listing = client.station_list_with_device()
    inverters = _device_rows(listing)
    if not inverters:
        stations = client.station_list()
        station_ids = []
        for node, _, _ in _walk_with_station(stations):
            sid = node.get("stationId") or (
                node.get("id") if "stationName" in node or "name" in node else None
            )
            if isinstance(sid, int) or (isinstance(sid, str) and str(sid).isdigit()):
                station_ids.append(int(sid))
        unique_ids = list(dict.fromkeys(station_ids))
        if unique_ids:
            devices = client.post(
                "/station/device",
                {"page": 1, "size": 50, "stationIds": unique_ids},
            )
            inverters = _device_rows(devices)

    if preferred_sn:
        for row in inverters:
            if row["deviceSn"] == preferred_sn:
                return row
        station_id = inverters[0]["stationId"] if inverters else None
        station_name = inverters[0]["stationName"] if inverters else None
        return {
            "deviceSn": preferred_sn,
            "deviceType": "INVERTER",
            "stationId": station_id,
            "stationName": station_name,
            "productId": None,
        }

    if len(inverters) == 1:
        return inverters[0]
    if not inverters:
        raise DeyeError("No inverter found on this account.")
    raise DeyeError(
        "Multiple inverters; set DEYE_DEVICE_SN. Found: "
        + ", ".join(row["deviceSn"] for row in inverters)
    )
