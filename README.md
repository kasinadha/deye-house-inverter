# Deye house inverter CLI

This repo talks to a **Deye hybrid inverter** through the official **DeyeCloud OpenAPI**. Its job is to **cut grid import** without selling power to the grid, by telling the inverter when it may use the battery and when it must charge from the grid.

It is a small **Python command-line tool**. There is no website and no phone-app plugin. After you run `apply` once, the schedule lives **on the inverter**. You do not need this program running 24/7.

Use this if you have a Deye hybrid (PV + battery + grid) on DeyeCloud and you want a simple SOC floor policy instead of default “sell” or “always import” behaviour.

## What the code does

DeyeCloud does not run a live “if SOC then …” script in the cloud. This CLI **writes inverter settings** that implement the policy natively:

1. **Zero export** — work mode `ZERO_EXPORT_TO_LOAD`, max sell / zero-export power `0`, solar sell off.
2. **Time-of-use (TOU)** — six daily slots. Each slot’s **SOC** is the floor for that window: above it, the house runs on PV + battery; below it, the inverter may import from the grid until that SOC is reached.
3. **Hard battery low** — `BATT_LOW` must be **as low as the lowest TOU floor**, or the inverter will refuse to discharge that far.
4. **Grid charge on** — required so a low SOC can recover from the grid. The TOU SOC is what **stops** grid charging.

Commands:

| Command | Effect |
|---|---|
| `python3 -m deye_house --villa villa431 status` | Read live power/SOC. **No writes.** |
| `python3 -m deye_house --villa villa431 apply --dry-run` | Same as status. |
| `python3 -m deye_house --villa villa431 apply` | Write the policy to **your** inverter, then verify. |
| `python3 -m deye_house --villa villa431 verify` | Exit non-zero if the inverter config does not match the code. |

Python 3.10+, standard library only (`urllib`). No pip packages required.

## Policy shipped in this repo

These numbers are for **one house in India** (`Asia/Kolkata`). Treat them as an example, not a universal default.

| When (local time) | Battery floor | Meaning |
|---|---|---|
| 09:00–16:00 | **40%** | Use solar + battery first; import only if SOC &lt; 40%. |
| 16:00–09:00 | **60%** | Hold a higher reserve overnight; import only if SOC &lt; 60%. |

At 16:00, if SOC is still below 60%, grid charge brings it back up. PV may always charge above the floor. Export stays 0.

TOU slots actually sent (each slot lasts until the next):

| Start | SOC |
|---|---|
| 00:00 | 60% |
| 04:00 | 60% |
| 09:00 | 40% |
| 12:00 | 40% |
| 16:00 | 60% |
| 20:00 | 60% |

## What every user must set (credentials)

Do **not** reuse someone else’s credentials. That would control **their** plant.

**Git branches cannot hide secrets.** Anyone who can clone this public repo can fetch a `villa431` branch and read whatever was committed. Collaborators on a private repo can also see every branch. Git history keeps secrets even after you delete the branch. Do not store passwords on `villa431` or any other git branch.

Keep credentials in a **local file that git ignores**:

```bash
cp .env.example .env.villa431          # your house; never git add this
cp .env.example .env.villa-yourname    # a friend, only on their own laptop
python3 -m deye_house --villa villa431 status
python3 -m deye_house --villa villa-yourname apply --dry-run
```

`--villa NAME` loads `.env.NAME`. You can also pass `--env path/to/file`. Default is `.env`.

1. Install [Deye Cloud](https://www.deyecloud.com/) on the same account the inverter already uses.
2. Create an OpenAPI app at [developer.deyecloud.com/app](https://developer.deyecloud.com/app) in the **same datacenter as that account**.
3. Copy `.env.example` to `.env.villa431` (or `.env`) and fill:

```
DEYE_APP_ID=          # from the developer portal
DEYE_APP_SECRET=      # from the developer portal; never commit or WhatsApp this
DEYE_EMAIL=           # DeyeCloud login
DEYE_PASSWORD=        # plaintext here; the CLI SHA-256 hashes it for the API
DEYE_DEVICE_SN=       # optional; leave empty to auto-pick the first inverter
DEYE_BASE_URL=        # optional; see region below
```

`.env` and `.env.*` are gitignored (except `.env.example`). Never commit them.

**Region:** this repo defaults to India:

`https://india-developer.deyecloud.com/v1.0`

EU and US hosts reject an India App ID, and the reverse is also true. If your Deye account is not India, set `DEYE_BASE_URL` to your region (for example `https://eu1-developer.deyecloud.com/v1.0` or `https://us1-developer.deyecloud.com/v1.0`) and create the App ID on **that** developer portal.

If the account has more than one inverter, set `DEYE_DEVICE_SN` so you do not program the wrong machine.

## What to fine-tune for your house

Almost all behaviour lives in **`deye_house/policy.py`**. Change it, run tests, then `apply`.

| You want to change | Edit | Notes |
|---|---|---|
| Day vs night hours | `DAY_START`, `DAY_END` **and** `TOU_SLOTS` times | Deye has **exactly six** TOU slots. Slot times must line up with your window (a slot lasts until the next start). `DAY_START`/`DAY_END` only affect `status` labels; the inverter follows `TOU_SLOTS`. |
| How low the battery may go in the day | `SOC_FLOOR_DAY` and the daytime rows in `TOU_SLOTS` | Also set `BATT_LOW` to the **lowest** floor you use. |
| Overnight reserve | `SOC_FLOOR_NIGHT` and night rows in `TOU_SLOTS` | Typical 50–80%. Higher = more grid import at night, more backup left. |
| Clock / timezone | `SITE_TZ` | Use the IANA zone of the site (`Asia/Kolkata`, `Europe/Berlin`, …). |
| Charge power in a TOU slot | `TOU_POWER_W` | Do not exceed the inverter’s charge rating (this example uses 6000 W for a 6 kW hybrid). |
| Which weekdays TOU is on | `TOU_DAYS` | Default is every day. |
| Sell to grid | `WORK_MODE`, `MAX_SELL_POWER`, solar-sell order | This repo is built for **no export**. Changing that is a different policy. |
| Energy pattern | `ENERGY_PATTERN` | `LOAD_FIRST` vs `BATTERY_FIRST` changes PV vs battery priority. Leave `LOAD_FIRST` unless you know you need the other. |

After editing:

```bash
python3 -m unittest discover -s tests
python3 -m deye_house apply --dry-run   # inspect current vs new target
python3 -m deye_house apply             # write to the inverter
```

`status` / `verify` compare the cloud config to **whatever is currently in `policy.py`**. If you change the policy and do not `apply`, verify will fail until the inverter is updated.

## Setup and run

```bash
git clone -b feat/60-soc-floor-cli https://github.com/kasinadha/deye-house-inverter.git
cd deye-house-inverter
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
cp .env.example .env.villa431   # pick any name; this file stays on your laptop
# edit .env.villa431, then:
python3 -m deye_house --villa villa431 status
```

Orders are sent **one at a time**. The cloud rejects overlapping writes (`2104004`). Each order is polled until `status=666`. `/config/*` can lag 10–30 seconds; `apply` re-reads until it matches.

## Safety

- `apply` **changes the live inverter**. Start with `status` and `--dry-run`.
- Keep export at 0 unless you are sure your utility allows feed-in.
- Do not set `BATT_LOW` higher than your lowest TOU SOC, or daytime discharge will stop early.
- Do not share App Secret, password, or tokens.

## Deye API

- Catalog: https://developer.deyecloud.com/api
- This client’s default OpenAPI: https://india-developer.deyecloud.com/v2/api-docs
