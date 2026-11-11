"""Tests for the Custom Meter implementation."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.evse_load_balancer import config_flow as cf
from custom_components.evse_load_balancer.meters.custom_meter import CustomMeter
from custom_components.evse_load_balancer.meters.meter import Phase

L1_SENSORS = {
    cf.CONF_PHASE_SENSOR_CONSUMPTION: "sensor.l1_consumption",
    cf.CONF_PHASE_SENSOR_PRODUCTION: "sensor.l1_production",
    cf.CONF_PHASE_SENSOR_VOLTAGE: "sensor.l1_voltage",
}


@pytest.fixture
def states():
    """States of the sensors of phase one, in kW and V."""
    return {
        "sensor.l1_consumption": "3.45",
        "sensor.l1_production": "0",
        "sensor.l1_voltage": "230",
    }


@pytest.fixture
def mock_hass(states):
    hass = MagicMock()
    hass.states.get.side_effect = lambda entity_id: (
        SimpleNamespace(state=states[entity_id]) if entity_id in states else None
    )
    return hass


@pytest.fixture
def mock_config_entry():
    return MockConfigEntry(
        domain="evse_load_balancer",
        title="Custom Test Meter",
        data={
            cf.CONF_CUSTOM_PHASE_CONFIG: True,
            cf.CONF_PHASE_COUNT: 1,
            cf.CONF_PHASE_KEY_ONE: L1_SENSORS,
        },
        unique_id="test_custom_meter",
    )


@pytest.fixture
def custom_meter(mock_hass, mock_config_entry):
    return CustomMeter(hass=mock_hass, config_entry=mock_config_entry)


def test_get_active_phase_current(custom_meter):
    # 3.45 kW at 230 V is 15 A
    assert custom_meter.get_active_phase_current(Phase.L1) == 15


def test_get_active_phase_current_with_production(custom_meter, states):
    states["sensor.l1_consumption"] = "0"
    states["sensor.l1_production"] = "2.3"
    assert custom_meter.get_active_phase_current(Phase.L1) == -10


def test_get_active_phase_current_unconfigured_phase(custom_meter):
    assert custom_meter.get_active_phase_current(Phase.L2) is None


@pytest.mark.parametrize("missing_state", [STATE_UNAVAILABLE, STATE_UNKNOWN, "n/a"])
def test_get_active_phase_current_none(custom_meter, states, missing_state):
    states["sensor.l1_consumption"] = missing_state
    assert custom_meter.get_active_phase_current(Phase.L1) is None


def test_get_active_phase_current_missing_sensor(custom_meter, states):
    del states["sensor.l1_voltage"]
    assert custom_meter.get_active_phase_current(Phase.L1) is None


def test_get_tracking_entities(custom_meter):
    """Only the sensors of the configured phases are tracked."""
    assert sorted(custom_meter.get_tracking_entities()) == sorted(L1_SENSORS.values())
