# Deye house inverter — SOC floors, minimize grid import
#
# Official India OpenAPI only. Do not add this to dendukuri-residences.
# Secrets: DEYE_APP_ID, DEYE_APP_SECRET, DEYE_EMAIL, DEYE_PASSWORD (never commit).
#
# Policy (Asia/Kolkata):
# - 09:00–16:00: SOC floor 40%. Use PV+battery above 40%; grid only if SOC < 40%.
# - Otherwise: SOC floor 60%. Use PV+battery above 60%; grid only if SOC < 60%.
# - At the active floor: hold. PV may still charge above it.
# - At 16:00, if SOC is below 60%, grid charge restores to 60%.
# - Export stays 0.
#
# TOU slots (each lasts until the next):
#   00:00 soc=60, 04:00 soc=60, 09:00 soc=40, 12:00 soc=40, 16:00 soc=60, 20:00 soc=60
# BATT_LOW=40 so daytime discharge to 40% is allowed. Night floor is TOU soc=60.
#
# Commands (one order at a time; poll GET /order/{id} until status 666):
# 1. POST /order/sys/workMode/update ZERO_EXPORT_TO_LOAD
# 2. POST /order/sys/energyPattern/update LOAD_FIRST
# 3. POST /order/battery/modeControl GRID_CHARGE on
# 4. POST /order/battery/parameter/update paramterType=BATT_LOW value=40 (official typo)
# 5. POST /order/sys/tou/update six slots as above, enableGridCharge true, power=6000
# 6. POST /order/sys/tou/switch on all days
# 7-8. POST /order/sys/power/update ZERO_EXPORT_POWER=0 and MAX_SELL_POWER=0
# 9. POST /order/sys/solarSell/control off
#
# Do not POST /strategy/dynamicControl with energyPattern (India 2101008).
# Base URL: https://india-developer.deyecloud.com/v1.0
