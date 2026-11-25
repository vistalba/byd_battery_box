# AGENTS.md – Arbeitsweise in diesem Repository

Leitfaden für Menschen und KI-Agenten (Claude Code, Copilot, Codex …), die an der
Home-Assistant-Integration **BYD Battery Box** (`custom_components/byd_battery_box`)
arbeiten. Projektdetails (Architektur, Register-Layout, Sensoren) stehen in
[`CLAUDE.md`](CLAUDE.md) und im [`README.md`](README.md).

## 1. Grundsätze

1. **Keine Breaking Changes.** Bestehende Installationen müssen nach einem Update
   unverändert weiterlaufen:
   - Entity-IDs, Unique-IDs (oder eine Registry-Migration), Attribut-Namen und
     -Formate, Einheiten und `state_class` bleiben stabil.
   - Konfigurationsdaten (`entry.data`) werden nur additiv erweitert; ältere Keys
     bleiben lesbar (Fallback), Migrationen sind abwärtskompatibel
     (`MINOR_VERSION` statt `VERSION` erhöhen, wenn möglich).
   - Werden Daten verschoben (z. B. Log-Speicher), gibt es eine automatische
     Migration.
2. **Best Practice vor Eigenbau:** Home-Assistant-Helfer verwenden
   (`DataUpdateCoordinator`, `CoordinatorEntity`, `EntityDescription`,
   `Store`, `issue_registry`, `diagnostics` …).
3. **Kein blockierendes I/O im Event-Loop.** Datei-I/O über
   `hass.async_add_executor_job` bzw. `Store`.
4. **Nur eine Modbus-Verbindung:** Die BYD-BMU akzeptiert nur eine gleichzeitige
   Verbindung. Jeder Code, der verbindet (Config-Flow, Reconfigure, Diagnose),
   muss das berücksichtigen und Verbindungen immer schliessen.
5. **Kleine, nachvollziehbare Commits** mit aussagekräftiger Message
   (Conventional Commits: `fix:`, `feat:`, `refactor:`, `test:`, `docs:`,
   `ci:`, `chore:`).

## 2. Home Assistant Integration Quality Scale

Ziel ist die Erfüllung möglichst aller Regeln der Quality Scale. Der Stand pro
Regel wird in
[`custom_components/byd_battery_box/quality_scale.yaml`](custom_components/byd_battery_box/quality_scale.yaml)
gepflegt (`done`, `todo` oder `exempt` mit Begründung).

| Thema | Link |
|---|---|
| Übersicht Quality Scale | https://developers.home-assistant.io/docs/core/integration-quality-scale/ |
| Alle Regeln | https://developers.home-assistant.io/docs/core/integration-quality-scale/rules |
| Checkliste | https://developers.home-assistant.io/docs/core/integration-quality-scale/checklist |
| Contributors-Doku (neu) | https://contributors.home-assistant.io/core/quality-scale/ |
| Config Flow | https://developers.home-assistant.io/docs/config_entries_config_flow_handler |
| Options Flow | https://developers.home-assistant.io/docs/config_entries_options_flow_handler |
| DataUpdateCoordinator | https://developers.home-assistant.io/docs/integration_fetching_data |
| Entities | https://developers.home-assistant.io/docs/core/entity |
| Sensor-Entities | https://developers.home-assistant.io/docs/core/entity/sensor |
| Entity-Registry / Unique IDs | https://developers.home-assistant.io/docs/entity_registry_index |
| Device-Registry | https://developers.home-assistant.io/docs/device_registry_index |
| Übersetzungen | https://developers.home-assistant.io/docs/internationalization/core |
| Icon-Übersetzungen | https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/icon-translations |
| Diagnostics | https://developers.home-assistant.io/docs/core/integration_diagnostics |
| Repairs | https://developers.home-assistant.io/docs/core/platform/repairs |
| Manifest | https://developers.home-assistant.io/docs/creating_integration_manifest |
| Tests | https://developers.home-assistant.io/docs/development_testing |

Kurzfassung der Stufen:

- **Bronze:** UI-Config-Flow mit Verbindungstest, Unique-IDs, `has_entity_name`,
  `runtime_data`, `coordinator.py`/`entity.py`, keine Doppel-Einträge,
  `ConfigEntryNotReady` beim Setup, Config-Flow-Tests, Grund-Doku.
- **Silver:** sauberes Entladen, Entities werden `unavailable`, einmaliges
  Logging bei Verbindungsverlust, `PARALLEL_UPDATES`, Exceptions in Actions,
  > 95 % Testabdeckung, Doku der Parameter.
- **Gold:** Devices, Diagnostics, Reconfigure-Flow, Repair-Issues,
  Entity-/Icon-/Exception-Übersetzungen, Entity-Kategorien/Device-Classes,
  selten genutzte Entities deaktiviert, erweiterte Doku.
- **Platinum:** asynchrone Library, strikte Typisierung (`mypy --strict`).

## 3. Skills & Referenzen

| Skill / Quelle | Link | Zweck |
|---|---|---|
| `ha-integration-dev` (aurora-smart-home) | https://github.com/tonylofgren/aurora-smart-home/tree/main/ha-integration-dev | Best-Practice-Checklisten: Coordinator, Config-Flow, Tests, Security, HACS |
| Skill-Datei | https://github.com/tonylofgren/aurora-smart-home/blob/main/ha-integration-dev/SKILL.md | „Iron Laws“ & Pre-Completion-Checkliste |
| pytest-homeassistant-custom-component | https://github.com/MatthewFlamm/pytest-homeassistant-custom-component | Test-Fixtures (`hass`, `MockConfigEntry` …) |
| HACS-Anforderungen | https://hacs.xyz/docs/publish/integration | Veröffentlichung via HACS |
| Brands | https://github.com/home-assistant/brands | Logo/Icon |
| BYD Modbus-Infos | https://github.com/sarnau/BYD-Battery-Box-Infos | Register-Doku |
| ioBroker BYD Hex-Struktur | https://github.com/christianh17/ioBroker.bydhvs/blob/master/docs/byd-hexstructure.md | Log-/Hex-Dekodierung |

Wichtigste Regeln aus dem Skill („Iron Laws“), verbindlich für dieses Repo:

- Zeitstempel zeitzonenbewusst (`homeassistant.util.dt` bzw.
  `datetime.now().astimezone()`), nie naive `datetime.now()` für Sensorwerte.
- State-Attribute nur JSON-serialisierbar; grosse Attribute in
  `_unrecorded_attributes`.
- Laufzeitdaten in `entry.runtime_data`, nie `hass.data[DOMAIN]`.
- `DataUpdateCoordinator(..., config_entry=entry)`.
- `EntityDescription`-Dataclasses mit `frozen=True, kw_only=True`.
- Unique-IDs nie aus IP/Hostname/Name ableiten → Seriennummer der BMU.
- Keine Secrets/Seriennummern in Logs oder Diagnostics ohne Redaction.

## 4. Repository-Struktur

```
custom_components/byd_battery_box/
├── __init__.py          # Setup/Unload/Migration
├── coordinator.py       # DataUpdateCoordinator (Polling BMU/BMS/Log)
├── entity.py            # Basis-Entity (CoordinatorEntity, device_info)
├── sensor.py / button.py
├── config_flow.py       # User-, Reconfigure- und Options-Flow
├── diagnostics.py       # Diagnose-Download (redacted)
├── log_store.py         # Persistenz der BYD-Logeinträge (Store + CSV-Export)
├── bydboxclient.py      # Modbus-Client & Dekodierung (HA-unabhängig)
├── extmodbusclient.py   # pymodbus-Wrapper
├── bydbox_const.py      # Hardware-Konstanten / Log-Codes
├── const.py             # HA-Konstanten
├── icons.json           # Icon-Übersetzungen
├── strings.json         # Quelle der Übersetzungen (= translations/en.json)
├── translations/        # en.json, de.json
└── quality_scale.yaml   # Stand der Quality-Scale-Regeln
tests/                   # pytest-homeassistant-custom-component
scripts/                 # Hilfsskripte (z. B. Modbus-Simulator)
```

Hinweis: Die Struktur entsteht schrittweise über die Phasen-Branches
(`claude/phase-1-…` bis `claude/phase-7-…`).

## 5. Entwicklungsumgebung & Checks

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt
```

Vor jedem Commit lokal ausführen:

```bash
ruff check custom_components/ tests/
python -m py_compile custom_components/byd_battery_box/*.py
mypy custom_components/
pytest
```

- Tests liegen in `tests/` und nutzen einen simulierten Modbus-Client
  (keine Hardware nötig). Neue Features brauchen Tests.
- Ziel-Testabdeckung: > 95 % pro Modul.
- Übersetzungen: `strings.json` ist die Quelle; `translations/en.json` muss
  identisch sein (Test prüft das).

## 6. Versionierung & Release

- Version steht in `manifest.json`, `pyproject.toml` und `CLAUDE.md`.
- **Nicht manuell erhöhen:** Die CI (`.github/workflows/ci.yaml`) erhöht die
  Patch-Version bei jedem Push auf `main` automatisch und erstellt ein Release.

## 7. Branches & Pull Requests

- Nie direkt auf `main` committen; Feature-Branches verwenden.
- PR-Beschreibung: Was, Warum, Wie getestet, Hinweise zur Migration.
- CI muss grün sein (Ruff, Syntax, HACS, Hassfest, Tests).
