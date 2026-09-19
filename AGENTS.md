# Deye house inverter — SOC floors, minimize grid import
#
# Official India OpenAPI only. Do not add this to dendukuri-residences.
# Secrets: DEYE_APP_ID, DEYE_APP_SECRET, DEYE_EMAIL, DEYE_PASSWORD (never commit).
#
# Policy (Asia/Kolkata):
# - Every TOU slot: SOC floor 40%, enableGridCharge false.
#   PV+battery supply the house above 40%. Grid covers *load* only after SOC
#   hits 40% — it must not charge the pack. Tick Grid Charge on a slot and a
#   full battery can sit idle while the house imports (2026-09-19 15:28 IST:
#   PV 3.36 kW, UPS 4.60 kW, grid 1.36 kW, battery 99% / 31 W).
# - Night SOC must not be high (70% did). TOU SOC is a discharge floor.
# - 09:00–16:00 is the sun-aware day window for status labels; floors match.
# - Export stays 0.
# - Global GRID_CHARGE master is OFF. Leaving it ON charged past TOU (~90%).
# - DeyeCloud Weather Shield / Force Charge can lock SOC at 80%+ from the app.
#   This CLI has no order for that; turn it off in the phone app if import
#   continues with a full pack.
#
# TOU slots (each lasts until the next):
#   00:00 soc=40 gridCharge=off, 04:00 soc=40 gridCharge=off,
#   09:00 soc=40 gridCharge=off, 12:00 soc=40 gridCharge=off,
#   16:00 soc=40 gridCharge=off, 20:00 soc=40 gridCharge=off
# BATT_LOW=40 so discharge to the lowest TOU floor is allowed.
#
# Commands (one order at a time; poll GET /order/{id} until status 666):
# 1. POST /order/sys/workMode/update ZERO_EXPORT_TO_LOAD
# 2. POST /order/sys/energyPattern/update LOAD_FIRST
# 3. POST /order/battery/modeControl GRID_CHARGE off
# 4. POST /order/battery/parameter/update paramterType=BATT_LOW value=40 (official typo)
# 5. POST /order/sys/tou/update six slots as above, enableGridCharge false, power=6000
# 6. POST /order/sys/tou/switch on all days
# 7-8. POST /order/sys/power/update ZERO_EXPORT_POWER=0 and MAX_SELL_POWER=0
# 9. POST /order/sys/solarSell/control off
#
# Do not POST /strategy/dynamicControl with energyPattern (India 2101008).
# Base URL: https://india-developer.deyecloud.com/v1.0
