# Deye house inverter CLI

Python CLI for the house hybrid inverter on **DeyeCloud India OpenAPI**. It applies a fixed energy policy:

- Keep **grid export at 0**
- Use PV + battery whenever SOC is **above 60%**
- Import from the grid **only** to restore SOC back to **60%**
- At 60%, hold the floor; PV may still charge above it

This is not the Dendukuri Residences rental app.

## Setup

```bash
cd deye-house-inverter
python3 -m venv .venv
source .venv/bin/activate
cp .env.example .env
```

Fill `.env` (never commit it):

```
DEYE_APP_ID=
DEYE_APP_SECRET=
DEYE_EMAIL=
DEYE_PASSWORD=
DEYE_DEVICE_SN=          # optional; discovered after login if empty
```

Password is stored in plaintext in `.env`. The CLI SHA-256 hashes it before `POST /account/token`.

India only: `https://india-developer.deyecloud.com/v1.0`. EU/US hosts reject this App ID.

## Commands

```bash
python3 -m deye_house status    # live telemetry + config, no writes
python3 -m deye_house apply     # write the 60% policy, then verify
python3 -m deye_house verify    # fail if config != target
python3 -m deye_house apply --dry-run
python3 -m unittest discover -s tests
```

No third-party packages. Python 3.10+ stdlib only.

## How the policy is written

Deye does not take a live “if SOC then …” script. The inverter is programmed so that behavior is native:

| Setting | Value |
|---|---|
| Work mode | `ZERO_EXPORT_TO_LOAD` |
| Energy pattern | `LOAD_FIRST` |
| Grid charge | ON (needed so SOC &lt; 60% can recover) |
| Battery low | `60` |
| TOU | ON every day, 6 slots, SOC target **60%**, grid+PV charge, 6000 W |
| Max sell / zero-export power | `0` |
| Solar sell | OFF |

Orders are sent **one at a time**. Overlapping writes return `2104004`. Each order is polled with `GET /order/{orderId}` until `status=666`.

`/config/*` can lag 10–30s after a successful order. `apply` re-reads until the target matches.

## Telemetry keys

`POST /device/latest` `dataList`:

| Policy field | API key |
|---|---|
| pvPower | `TotalDCInputPower` |
| loadPower | `TotalConsumptionPower` |
| batterySoc | `SOC` |
| gridPower | `TotalGridPower` (positive = import) |
| batteryPower | `BatteryPower` (positive = discharge) |

Known plant from this account: station `The sanctuary Villa 431` (`7982`), inverter `2508300228`.

## Docs

- Catalog: https://developer.deyecloud.com/api
- OpenAPI: https://india-developer.deyecloud.com/v2/api-docs
