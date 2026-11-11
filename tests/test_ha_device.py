"""Tests for the shared Home Assistant device helpers."""

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN

from custom_components.evse_load_balancer.ha_device import HaDevice, parse_amps


@pytest.fixture
def ha_device():
    device = HaDevice(hass=MagicMock(), device_entry=MagicMock())
    device.entities = [
        SimpleNamespace(
            entity_id="sensor.charger_limit",
            unique_id="abc_limit",
            translation_key="limit",
            disabled=False,
        ),
        SimpleNamespace(
            entity_id="sensor.charger_status",
            unique_id="abc_status",
            translation_key="status",
            disabled=True,
        ),
    ]
    return device


@pytest.mark.parametrize(
    ("state", "expected"),
    [("16", 16), ("16.0", 16), (16, 16), (6.9, 6), (None, None), ("n/a", None)],
)
def test_parse_amps(state, expected):
    assert parse_amps(state) == expected


def test_get_entity_state(ha_device):
    ha_device.hass.states.get.return_value = SimpleNamespace(state="16.5")
    assert ha_device._get_entity_state_by_key("limit") == "16.5"
    assert ha_device._get_entity_state_by_key("limit", float) == 16.5
    ha_device.hass.states.get.assert_called_with("sensor.charger_limit")


@pytest.mark.parametrize("state", [STATE_UNAVAILABLE, STATE_UNKNOWN])
def test_get_entity_state_without_value(ha_device, state):
    """An entity that is unavailable or unknown has no value to work with."""
    ha_device.hass.states.get.return_value = SimpleNamespace(state=state)
    assert ha_device._get_entity_state_by_key("limit") is None
    assert ha_device._get_entity_state_by_key("limit", float) is None


def test_get_entity_state_missing(ha_device):
    ha_device.hass.states.get.return_value = None
    assert ha_device._get_entity_state_by_translation_key("limit") is None


def test_get_entity_state_unparsable(ha_device):
    ha_device.hass.states.get.return_value = SimpleNamespace(state="n/a")
    assert ha_device._get_entity_state_by_unique_id("abc_limit", float) is None


def test_entity_not_found(ha_device):
    with pytest.raises(ValueError):
        ha_device._get_entity_id_by_key("does_not_exist")


def test_disabled_entity_is_reported_once(ha_device, caplog):
    """A disabled entity is looked up every second, but only reported once."""
    caplog.set_level(logging.ERROR)
    for _ in range(5):
        assert ha_device._get_entity_id_by_key("status") == "sensor.charger_status"
        assert (
            ha_device._get_entity_id_by_translation_key("status")
            == "sensor.charger_status"
        )

    assert caplog.text.count("Required entity sensor.charger_status is disabled") == 1
