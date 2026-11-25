"""Consistency checks of translations and icons."""

from __future__ import annotations

import json
import re
from pathlib import Path

from custom_components.byd_battery_box.button import BUTTONS
from custom_components.byd_battery_box.sensor import BMS_SENSORS, BMU_SENSORS, CONNECTION_SENSORS

BASE = Path(__file__).resolve().parents[1] / "custom_components" / "byd_battery_box"


def _load(name: str) -> dict:
    return json.loads((BASE / name).read_text(encoding="utf-8"))


def _keys(data: dict, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            keys |= _keys(value, path)
        else:
            keys.add(path)
    return keys


def test_entity_translations_complete() -> None:
    """Every entity description has a translated name and vice versa."""
    en = _load("translations/en.json")
    sensor_keys = {d.translation_key for d in (*BMU_SENSORS, *CONNECTION_SENSORS, *BMS_SENSORS)}
    assert sensor_keys == set(en["entity"]["sensor"])
    assert {d.translation_key for d in BUTTONS} == set(en["entity"]["button"])


def test_icons_reference_entities() -> None:
    """Every icon belongs to an entity translation key."""
    en = _load("translations/en.json")
    icons = _load("icons.json")
    for platform, entries in icons["entity"].items():
        assert set(entries) <= set(en["entity"][platform]), platform


def test_german_translation_consistent() -> None:
    """The German translation only contains keys of the English one and keeps placeholders."""
    en = _load("translations/en.json")
    de = _load("translations/de.json")
    en_keys = _keys(en)
    de_keys = _keys(de)
    assert de_keys <= en_keys
    assert {k for k in en_keys if not k.startswith("entity.")} == de_keys
    flat_en = {k: v for k, v in _flatten(en)}
    for key, value in _flatten(de):
        assert set(re.findall(r"{\w+}", value)) == set(re.findall(r"{\w+}", flat_en[key])), key
        assert "ß" not in value


def _flatten(data: dict, prefix: str = ""):
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            yield from _flatten(value, path)
        else:
            yield path, value


async def test_icons_and_translations_load(hass, setup_entry) -> None:
    """Home Assistant loads the icons and translations of the integration."""
    from homeassistant.helpers.icon import async_get_icons  # noqa: PLC0415
    from homeassistant.helpers.translation import async_get_translations  # noqa: PLC0415

    icons = await async_get_icons(hass, "entity", integrations=["byd_battery_box"])
    assert icons["byd_battery_box"]["sensor"]["connection_health"]["state"]["unhealthy"] == "mdi:close-circle"
    translations = await async_get_translations(hass, "de", "exceptions", integrations=["byd_battery_box"])
    assert "component.byd_battery_box.exceptions.not_reachable.message" in translations
    entity = await async_get_translations(hass, "en", "entity", integrations=["byd_battery_box"])
    assert entity["component.byd_battery_box.entity.sensor.soc.name"] == "State of charge"
