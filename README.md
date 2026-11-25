[![CI](https://github.com/TimWeyand/byd_battery_box/actions/workflows/ci.yaml/badge.svg)](https://github.com/TimWeyand/byd_battery_box/actions/workflows/ci.yaml)
[![GitHub Release](https://img.shields.io/github/v/release/TimWeyand/byd_battery_box)](https://github.com/TimWeyand/byd_battery_box/releases/latest)
[![HACS](https://img.shields.io/badge/HACS-Default-orange.svg)](https://hacs.xyz/)
[![License](https://img.shields.io/github/license/TimWeyand/byd_battery_box)](LICENSE.md)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2025.9%2B-blue.svg)](https://www.home-assistant.io/)
[![GitHub Issues](https://img.shields.io/github/issues/TimWeyand/byd_battery_box)](https://github.com/TimWeyand/byd_battery_box/issues)

# byd_battery_box
Home assistant Custom Component for reading data from BYD Battery Box system series like HVL, HVM, HVS, LVS. This integration uses a local modbus connection.

> [!NOTE]
> This is a fork of [redpomodoro/byd_battery_box](https://github.com/redpomodoro/byd_battery_box). This fork has diverged from the original project and includes additional features, bug fixes, and improvements that are not available upstream.

> [!CAUTION]
> This is a work in progress project - it is still in early development stage, so there are still breaking changes possible.
>
> This is an unofficial implementation and not supported by BYD. It might stop working at any point in time.
> You are using this module (and it's prerequisites/dependencies) at your own risk. Not me neither any of contributors to this or any prerequired/dependency project are responsible for damage in any kind caused by this project or any of its prerequsites/dependencies.

> [!IMPORTANT]
> The battery must be connected by LAN cable as the wireless connection disables itself after a timeout. The default IP address of the BYD battery is 192.168.16.254. Later firmware versions seem to support DHCP and will use the assigned IP address. In the later case you will need to look up the address. Depending on your network configuration a static route might be added.  You can test connectivity to the battery in the browser by using the batteries address for example http://192.168.16.254 and should get a login page. 

> [!IMPORTANT]
> Note using other applications connecting to battery simulatousnely might give unexpected results. 

# Installation

## HACS (recommended) 

This integration is available in [HACS](https://hacs.xyz/) (Home Assistant Community Store).

<small>*HACS is a third party community store and is not included in Home Assistant out of the box.*</small>

[![Open your Home Assistant instance and open this repository in HACS (Integration).](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=TimWeyand&repository=byd_battery_box&category=integration)

## Manual install

1. Download the latest release and copy the folder `custom_components/byd_battery_box` to your Home Assistant `config/custom_components` folder.
2. Restart Home Assistant.
3. Add the integration via **Settings → Devices & services → Add integration → BYD Battery Box** (see *Configuration*).

# Supported devices

| Series | Type | Status |
| --- | --- | --- |
| Battery-Box Premium **HVS** | HV, modules in series | Supported |
| Battery-Box Premium **HVM** | HV, modules in series | Supported |
| Battery-Box Premium **HVL** | HV | Basic data (no cell data, model has no cell specification) |
| Battery-Box Premium **LVS** | LV, modules in parallel | Supported |
| LV Flex / LVS Lite / LVL | LV | Not tested, battery type might not be detected (`model` = `NA`) |

Up to 3 towers (BMS) per BMU are supported. The integration talks to the **BMU** (Battery Management Unit) via Modbus TCP (Modbus RTU frames over TCP, default port `8080`).

# Prerequisites

- The BMU must be reachable from Home Assistant via **LAN cable** (the WiFi of the BMU switches off after a while).
- Default IP address of the BMU: `192.168.16.254` (newer firmware also supports DHCP). A static route might be required.
- The BMU accepts **only one Modbus connection**. Close BE Connect or other tools/integrations reading the battery, otherwise the setup fails or data is missing.

# Configuration

After installation go to **Settings → Devices & services → Add integration → BYD Battery Box**.

| Field | Default | Description |
| --- | --- | --- |
| Name | `BYD Battery Box` | Name of the integration entry |
| IP Address | – | IP address or host name of the BMU |
| Port | `8080` | Modbus TCP port of the BMU |
| Modbus Unit/Slave ID | `1` | Modbus unit id of the BMU |
| Scan Interval BMU | `30` s (min. 10 s) | Main values (SOC, power, voltage, current, temperatures) |
| Scan Interval BMS | `600` s (min. 60 s) | Detailed tower data (cell voltages, cell temperatures, balancing) |
| Scan Interval log data | `600` s (min. 120 s) | New log entries |

The connection is tested before the entry is created. A battery (serial number) can only be added once.

## Options

**Settings → Devices & services → BYD Battery Box → Configure** changes the three scan intervals. The integration reloads automatically.

## Reconfigure

**⋮ → Reconfigure** changes IP address, port and unit id without removing the integration (e.g. after the battery got a new IP address). The integration is stopped while the new settings are tested; if another battery answers (different serial number) the change is refused.

# Data updates

The integration polls the battery (local polling, no cloud):

- **BMU status** every 30 s (configurable): SOC, SOH, power, current, voltages, temperatures, energy counters.
- **BMS status** every 10 minutes (configurable): per tower cell voltages/temperatures, balancing, warnings, errors. Reading a tower takes a few seconds, therefore the longer interval.
- **Log data** every 10 minutes (configurable). With the same interval the static data (number of towers, modules, model) is re-read; towers added later appear automatically.

If the BMU does not answer 3 times in a row, the entities become *unavailable* (the connection health sensors stay available) and recover automatically when the battery answers again. Lost and restored connections are logged once.

# Log data
The log data is by default updated every 10 minutes. Log entries are stored in the Home Assistant storage (`/config/.storage/byd_battery_box.<entry_id>.log`) so they survive updates of the integration. For convenience a CSV export is written to `/config/byd_battery_box/<name>_log.csv` (e.g. `byd_battery_box_log.csv`). Entries older than 30 days are removed.

Log files of older versions (`/config/custom_components/byd_battery_box/logs/byd_log.json`) are migrated automatically on the first start.

Use the buttons on the devices to retrieve additional log history, during the update all other data updates will be suspended. The integration writes warnings into log to see progress of the updates.


# Usage

> FAQ: Why isn’t the dashboard under custom_components?
> The dashboard is a Lovelace frontend plugin (HACS category "plugin"). Frontend resources are JavaScript files, not Python integrations. Therefore it correctly lives under `byd_battery_box_dashboard/` and will be installed by HACS into `/www/community/byd_battery_box_dashboard/`.


### Battery Management Unit (BMU)

#### Sensors
| Entity | Description | Unit |
| --- | --- | --- |
| State of charge | Battery state of charge | % |
| State of health | Battery state of health | % |
| BMU temperature | BMU board temperature | °C |
| BMU cell temperature max | Highest cell temperature across all towers | °C |
| BMU cell temperature min | Lowest cell temperature across all towers | °C |
| BMU cell voltage max | Highest cell voltage across all towers | V |
| BMU cell voltage min | Lowest cell voltage across all towers | V |
| BMU current | Battery current (positive = charging) | A |
| BMU battery voltage | Battery bus voltage | V |
| BMU output voltage | Output voltage to inverter | V |
| BMU power | Current power (positive = charging) | W |
| Charge total energy | Lifetime total energy charged | kWh |
| Discharge total energy | Lifetime total energy discharged | kWh |
| Efficiency | Charge/discharge efficiency | % |

#### Diagnostic
| Entity | Description |
| --- | --- |
| Inverter | Connected inverter model |
| BMU version | BMU firmware version |
| BMU version A / B | BMU firmware version per slot |
| BMS version | BMS firmware version |
| Towers | Number of battery towers |
| Modules | Number of modules per tower |
| Application | Application type |
| Phase | Connection phase |
| Errors | Current error codes |
| Total capacity | Total battery capacity (kWh) |
| Param table version | Parameter table version |
| Cells per module | Number of cells per module |
| Temperature sensors per module | Number of temperature sensors per module |
| Updated | Last data update timestamp |
| BMU last log | Last BMU log entry |
| Log entries | Total log entries (with log list as attribute) |

### Battery Management System (BMS, per tower)

#### Sensors
| Entity | Description | Unit |
| --- | --- | --- |
| Cell voltage max / min | Highest/lowest cell voltage in tower | V |
| Cell voltage max/min number | Cell ID with highest/lowest voltage | - |
| Cell temperature max / min | Highest/lowest cell temperature in tower | °C |
| Cell temperature max/min number | Cell ID with highest/lowest temperature | - |
| State of charge | Tower SOC | % |
| State of health | Tower SOH | % |
| Current | Tower current | A |
| Battery voltage | Tower battery voltage | V |
| Output voltage | Tower output voltage | V |
| Charge total energy | Tower lifetime charge energy | kWh |
| Discharge total energy | Tower lifetime discharge energy | kWh |
| Efficiency | Tower charge/discharge efficiency | % |
| Cells balancing | Number of cells currently balancing | - |
| Cells average voltage | Average cell voltage | V |
| Cells average temperature | Average cell temperature | °C |
| Max/Min history cell voltage | Historical max/min cell voltage | V |
| Balancing total | Total balancing events | - |

#### Diagnostic
| Entity | Description |
| --- | --- |
| Warnings | Current warning codes |
| Errors | Current error codes |
| Updated | Last BMS data update timestamp |
| Last log | Last BMS log entry |

### Connection Health Monitoring

| Entity | Description | Unit |
| --- | --- | --- |
| Connection Quality | Modbus connection success rate | % |
| Last Latency | Last measured Modbus round-trip time | ms |
| Average Latency | Average Modbus round-trip time | ms |
| Consecutive Failures | Number of consecutive connection failures | - |
| Connection Health | Overall connection health status | - |


### BYD Battery Box Visualization (Lovelace Card)

For a rich, interactive dashboard experience, check out the companion Lovelace card: [BYD Battery Box Visualization](https://github.com/TimWeyand/byd_battery_box_visualization)

![BYD Battery Box Visualization Preview](https://raw.githubusercontent.com/TimWeyand/byd_battery_box_visualization/main/images/preview.png "BYD Battery Box Visualization")

Features:
- Visualize modules and cells with current, min/max voltages and temperatures
- Per-cell voltage bars with balancing indicators
- SOC bar with animated charge/discharge status
- Support for up to 3 battery towers
- Toggle between voltage (mV) and temperature view
- Interactive tooltips on hover/click
- Install via HACS as a Frontend/Lovelace plugin

[![Open your Home Assistant instance and open this repository in HACS (Frontend/Lovelace).](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=TimWeyand&repository=byd_battery_box_visualization&category=frontend)

---

### Markdown Cards

![log](images/log.png?raw=true "log")
```
      - type: grid
        cards:
          - type: markdown
            style: |
              ha-card {
                width: 100%;
              }
            content: >
              {% if states('sensor.log_entries') | is_number %} {% set log =
              state_attr('sensor.log_entries','log')%} | Timestamp | Unit | Code |
              Description | Details |

              |:---|:---|---:|:---|:---|

              {% for l in log %} |{{ l['ts'] }}|{{ l['u'] }}|{{ l['c'] }}|{{
              l['d'] }}|{{ l['detail'] }}|

              {% endfor %} {% endif %}
            title: Log
            grid_options:
              columns: full
              rows: auto
        column_span: 2
```

![cell_voltages](images/cell_voltages.png?raw=true "cell_voltages")

Voltages Table in mV
```
      - type: grid
        cards:
          - type: markdown
            style: |
              ha-card {
                width: 100%;
              }
            content: >
              {% if states('sensor.bms_1_cells_average_voltage') | is_number %}
              {% set
              sensors=['sensor.bms_1_cells_average_voltage','sensor.bms_2_cells_average_voltage','sensor.bms_3_cells_average_voltage']%}
              {% set cell_count = int(states('sensor.cells_per_module')) %}  {%
              for u in range(1,int(states('sensor.towers'))+1)%} 

              {% set modules = state_attr(sensors[u-1],'cell_voltages')%} | BMS
              {{u}} |{% for i in range(1,cell_count+1)%}Cell {{i}}|{%- endfor %}

              |:---|{% for i in range(1,cell_count+1) %}---:|{% endfor %}

              {% for m in modules %}{% set cells =  m['v'] %}|Module {{ m['m']
              }}|{% for v in cells %}{{ v }}|

              {%- endfor %}

              {% endfor %}

              {%- endfor %} {% endif %}
            title: Cell Voltages in mV
            grid_options:
              columns: full
              rows: auto
        column_span: 2
```
Voltages Table in V
```
      - type: grid
        cards:
          - type: markdown
            style: |
              ha-card {
                width: 100%;
              }
            content: >
              {% set
              sensors=['sensor.bms_1_cells_average_voltage','sensor.bms_2_cells_average_voltage','sensor.bms_3_cells_average_voltage']%}
              {% set cell_count = int(states('sensor.cells_per_module')) %}  {%
              for u in range(1,int(states('sensor.towers'))+1)%} 

              {% set modules = state_attr(sensors[u-1],'cell_voltages')%} | BMS
              {{u}} |{% for i in range(1,cell_count+1)%}Cell {{i}}|{%- endfor %}

              |:---|{% for i in range(1,cell_count+1) %}---:|{% endfor %}

              {% for m in modules %}{% set cells =  m['v'] %}|Module {{ m['m']
              }}|{% for v in cells %}{{ '%.3f' | format(v/1000) }}|

              {%- endfor %}

              {% endfor %}

              {%- endfor %}
            title: Cell Voltages in V
            grid_options:
              columns: full
              rows: auto
        column_span: 2
```

![cell_temperatures](images/cell_temperatures.png?raw=true "cell_temperatures")

Temperatures Table
```
      - type: grid
        cards:
          - type: markdown
            style: |
              ha-card {
                width: 100%;
              }
            content: >
              {% if states('sensor.bms_1_cells_average_temperature') | is_number
              %} {% set
              sensors=['sensor.bms_1_cells_average_temperature','sensor.bms_2_cells_average_temperature','sensor.bms_3_cells_average_temperature']%}
              {% set cell_count = int(int(states('sensor.cells_per_module')) /
              2) %}  {% for u in range(1,int(states('sensor.towers'))+1)%} 

              {% set modules = state_attr(sensors[u-1],'cell_temps')%} | BMS
              {{u}} |{% for i in range(1,cell_count+1)%}Cell
              {{i*2-1}}-{{i*2}}|{%- endfor %}

              |:---|{% for i in range(1,cell_count+1) %}---:|{% endfor %}

              {% for m in modules %}{% set cells =  m['t'] %}|Module {{ m['m']
              }}|{% for t in cells %}{{ t }}|

              {%- endfor %}

              {% endfor %}

              {%- endfor %}               {% endif %}
            title: Cell Temperatures in °C
            grid_options:
              columns: full
              rows: auto
        column_span: 2
```

![cell_balancing count](images/cell_balancing_count.png?raw=true "cell_balancing_count")

```
      - type: grid
        cards:
          - type: markdown
            style: |
              ha-card {
                width: 100%;
              }
            content: >
              {% if states('sensor.bms_1_balancing_total') | is_number %} {% set
              sensors=['sensor.bms_1_balancing_total','sensor.bms_2_balancing_total','sensor.bms_3_balancing_total']%}
              {% set cell_count = int(states('sensor.cells_per_module')) %}  {%
              for u in range(1,int(states('sensor.towers'))+1)%} 

              {% set modules = state_attr(sensors[u-1],'total_cells')%} | BMS
              {{u}} |{% for i in range(1,cell_count+1)%}Cell {{i}}|{%- endfor %}

              |:---|{% for i in range(1,cell_count+1) %}---:|{% endfor %}

              {% for m in modules %}{% set cells =  m['bct'] %}|Module {{ m['m']
              }}|{% for v in cells %}{{ v }}|

              {%- endfor %}

              {% endfor %}

              {%- endfor %} {% endif %}
            title: Cell Balancing Totals
            grid_options:
              columns: full
              rows: auto
        column_span: 2
```

![cell_balancing](images/cell_balancing.png?raw=true "cell_balancing")

```
      - type: grid
        cards:
          - type: markdown
            style: |
              ha-card {
                width: 100%;
              }
            content: >
              {% if states('sensor.bms_1_cells_balancing') | is_number %} {% set
              sensors=['sensor.bms_1_cells_balancing','sensor.bms_2_cells_balancing','sensor.bms_3_cells_balancing']%}
              {% set cell_count = int(states('sensor.cells_per_module')) %}  {%
              for u in range(1,int(states('sensor.towers'))+1)%} 

              {% set modules = state_attr(sensors[u-1],'cell_balancing')%} | BMS
              {{u}} |{% for i in range(1,cell_count+1)%}Cell {{i}}|{%- endfor %}

              |:---|{% for i in range(1,cell_count+1) %}---:|{% endfor %}

              {% for m in modules %}{% set cells =  m['b'] %}|Module {{ m['m']
              }}|{% for b in cells %}{% if b == 1%}on{%else%}-{%endif%}|

              {%- endfor %}

              {% endfor %}

              {%- endfor %} {% endif %}
            title: Cells Balancing
            grid_options:
              columns: full
              rows: auto
        column_span: 2

```


# Use cases & examples

- Monitor SOC, charge/discharge power and the energy counters in the **Energy dashboard** (`sensor.charge_total_energy`, `sensor.discharge_total_energy`).
- Watch the cell balance of each tower (`sensor.bms_1_cells_voltage_delta`) and get notified when it drifts.
- Get notified about warnings and errors of the BMU/BMS.

Notify when the cell voltage delta of tower 1 is above 50 mV for one hour:

```yaml
automation:
  - alias: "BYD cell delta high"
    triggers:
      - trigger: numeric_state
        entity_id: sensor.bms_1_cells_voltage_delta
        above: 50
        for: "01:00:00"
    actions:
      - action: notify.notify
        data:
          message: "BYD tower 1 cell delta is {{ states('sensor.bms_1_cells_voltage_delta') }} mV"
```

Notify on BMS warnings:

```yaml
automation:
  - alias: "BYD BMS warning"
    triggers:
      - trigger: state
        entity_id: sensor.bms_1_warnings
    conditions:
      - condition: template
        value_template: "{{ trigger.to_state.state not in ['Normal', 'unavailable', 'unknown'] }}"
    actions:
      - action: notify.notify
        data:
          message: "BYD warning: {{ trigger.to_state.state }}"
```

# Diagnostics

**Settings → Devices & services → BYD Battery Box → ⋮ → Download diagnostics** creates a file with the configuration, the current data and the connection health (IP address and serial number are redacted). Please attach it to issues.

# Troubleshooting

| Problem | Solution |
| --- | --- |
| *Failed to connect* during setup | Check IP address/port (`http://<ip>` should show the BMU login page), use a LAN cable, close BE Connect or other Modbus clients. |
| Entities are *unavailable* | The BMU did not answer 3 times in a row. Check the connection health sensors and the network. Another Modbus client may block the single connection. |
| Repair issue *configured more than once* | The same battery was added twice. Remove one of the entries. |
| BMS values update rarely | BMS data is read every 10 minutes by default, change it in the options (min. 60 s). |
| Log history incomplete | Use the *Update last … log entries* buttons; during the update all other updates are paused. |
| Debug logging | Add `custom_components.byd_battery_box: debug` and `pymodbus: debug` to the [logger](https://www.home-assistant.io/integrations/logger/) configuration. |

# Known limitations

- Only one Modbus connection at a time is accepted by the BMU.
- Read-only: no settings of the battery can be changed.
- HVL and some LV models (LV Flex, LVS Lite) are not fully supported (no cell data / type detection).
- Cell data of HVS modules (32 cells) is read with the 16-cell register layout of the known documentation.
- Log entries older than 30 days are removed from the local storage.
- The battery cannot be discovered automatically, the IP address has to be entered.

# Removal

1. **Settings → Devices & services → BYD Battery Box → ⋮ → Delete**.
2. Optional: remove the integration in HACS (or delete `custom_components/byd_battery_box`) and restart Home Assistant.
3. Optional: delete the CSV export folder `/config/byd_battery_box/`. The stored log entries in `.storage` are removed together with the integration entry.

# Upgrade notes (quality rework)

Existing installations keep their entity ids, history, statistics and attributes. Noticeable changes:

- Unique ids are now based on the BMU serial number (migrated automatically) – several batteries can be added.
- Entity names follow the Home Assistant naming (device name + entity name, e.g. *Battery Management Unit State of charge*). Entity ids are not changed.
- Icons are provided via icon translations; the `icon` state attribute is no longer set.
- Timestamps (`Updated` sensors) contain the time zone.
- Fixed values: *Cells per module* / *Temperature sensors per module* were swapped, latency sensors now really report milliseconds.
- Log storage moved from `custom_components/byd_battery_box/logs` (deleted by HACS updates) to `.storage` (see *Log data*).
- New installations: rarely used entities (BMU version A/B, param table version, last latency, log history 500/1000/2000 buttons) are disabled by default.
- Large attributes (cell voltages, temperatures, balancing, log list) are no longer written to the recorder database; they are still available as attributes.

# Example Devices
![bmu](images/bmu.png?raw=true "bmu")

![bms](images/bms.png?raw=true "bms")


# References
- https://github.com/redpomodoro/byd_battery_box - Original project (upstream)
- https://github.com/TimWeyand/byd_battery_box_visualization - Companion Lovelace visualization card
- https://github.com/sarnau/BYD-Battery-Box-Infos/blob/main/Read_Modbus.py
- https://github.com/christianh17/ioBroker.bydhvs/blob/master/docs/byd-hexstructure.md
- https://github.com/smarthomeNG/plugins/tree/develop/byd_bat
