# Deye house inverter — 60% SOC floor, minimize grid import
#
# Official India OpenAPI only. Do not add this to dendukuri-residences.
# Secrets: DEYE_APP_ID, DEYE_APP_SECRET, DEYE_EMAIL, DEYE_PASSWORD (never commit).
#
# Policy:
# - SOC > 60%: supply load from PV + battery. Grid charge OFF for this state
#   (TOU soc=60 with GRID_CHARGE enabled globally; inverter stops grid charge at 60%).
# - SOC < 60%: import from grid until SOC reaches 60%.
# - SOC == 60%: hold the floor. PV may still charge above 60%.
# - Export stays 0.
#
# Commands (one order at a time; poll GET /order/{id} until status 666):
# 1. POST /order/sys/workMode/update ZERO_EXPORT_TO_LOAD
# 2. POST /order/sys/energyPattern/update LOAD_FIRST
# 3. POST /order/battery/modeControl GRID_CHARGE on
# 4. POST /order/battery/parameter/update paramterType=BATT_LOW value=60 (official typo)
# 5. POST /order/sys/tou/update six slots soc=60 enableGridCharge true power=6000
# 6. POST /order/sys/tou/switch on all days
# 7-8. POST /order/sys/power/update ZERO_EXPORT_POWER=0 and MAX_SELL_POWER=0
# 9. POST /order/sys/solarSell/control off
#
# Do not POST /strategy/dynamicControl with energyPattern (India 2101008).
# Base URL: https://india-developer.deyecloud.com/v1.0
