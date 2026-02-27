"""Tests for the DSMR Meter implementation."""

from unittest.mock import MagicMock
import pytest
from homeassistant.helpers.device_registry import DeviceEntry
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.evse_load_balancer.meters.dsmr_meter import DsmrMeter
from custom_components.evse_load_balancer.meters.meter import Phase
from custom_components.evse_load_balancer import config_flow as cf


@pytest.fixture
def mock_hass():
    hass = MagicMock()
    return hass


@pytest.fixture
def mock_config_entry():
    return MockConfigEntry(
        domain="evse_load_balancer",
        title="DSMR Test Meter",
        data={"meter_type": "dsmr"},
        unique_id="test_dsmr_meter",
    )


@pytest.fixture
def mock_device_entry():
    device_entry = MagicMock(spec=DeviceEntry)
    device_entry.id = "dsmr_134"
    device_entry.identifiers = {("dsmr", "test_meter")}
    return device_entry


@pytest.fixture
def dsmr_meter(mock_hass, mock_config_entry, mock_device_entry):
    meter = DsmrMeter(
        hass=mock_hass,
        config_entry=mock_config_entry,
        device_entry=mock_device_entry,
    )
    meter.entities = []
    return meter


def test_get_active_phase_power_with_production(dsmr_meter):
    """Power = consumption - production when both entities exist."""
    dsmr_meter._get_entity_state_for_phase_sensor = MagicMock(
        side_effect=lambda _, s: 2.5 if s == cf.CONF_PHASE_SENSOR_CONSUMPTION else 0.5
    )
    result = dsmr_meter.get_active_phase_power(Phase.L1)
    assert result == 2.0


def test_get_active_phase_power_without_production(dsmr_meter):
    """Power = consumption when production entity is missing (no solar panels)."""
    dsmr_meter._get_entity_state_for_phase_sensor = MagicMock(
        side_effect=lambda _, s: 2.5 if s == cf.CONF_PHASE_SENSOR_CONSUMPTION else None
    )
    result = dsmr_meter.get_active_phase_power(Phase.L1)
    assert result == 2.5


def test_get_active_phase_power_missing_consumption(dsmr_meter):
    """Returns None when consumption entity is missing."""
    dsmr_meter._get_entity_state_for_phase_sensor = MagicMock(
        side_effect=lambda _, s: None if s == cf.CONF_PHASE_SENSOR_CONSUMPTION else 0.5
    )
    result = dsmr_meter.get_active_phase_power(Phase.L1)
    assert result is None


def test_get_active_phase_power_missing_all(dsmr_meter):
    """Returns None when all sensors are missing."""
    dsmr_meter._get_entity_state_for_phase_sensor = MagicMock(return_value=None)
    result = dsmr_meter.get_active_phase_power(Phase.L1)
    assert result is None


def test_get_active_phase_current(dsmr_meter):
    """Current = floor(power_W / voltage)."""
    dsmr_meter.get_active_phase_power = MagicMock(return_value=2.3)  # kW
    dsmr_meter._get_entity_state_for_phase_sensor = MagicMock(
        side_effect=lambda _, s: 230 if s == cf.CONF_PHASE_SENSOR_VOLTAGE else None
    )
    result = dsmr_meter.get_active_phase_current(Phase.L1)
    assert result == 10  # floor((2.3*1000)/230) = 10


def test_get_active_phase_current_missing_power(dsmr_meter):
    """Returns None when power is missing."""
    dsmr_meter.get_active_phase_power = MagicMock(return_value=None)
    dsmr_meter._get_entity_state_for_phase_sensor = MagicMock(
        side_effect=lambda _, s: 230 if s == cf.CONF_PHASE_SENSOR_VOLTAGE else None
    )
    result = dsmr_meter.get_active_phase_current(Phase.L1)
    assert result is None


def test_get_active_phase_current_missing_voltage(dsmr_meter):
    """Returns None when voltage is missing."""
    dsmr_meter.get_active_phase_power = MagicMock(return_value=2.3)
    dsmr_meter._get_entity_state_for_phase_sensor = MagicMock(return_value=None)
    result = dsmr_meter.get_active_phase_current(Phase.L1)
    assert result is None


def test_get_entity_id_for_phase_sensor_not_found(dsmr_meter):
    """Returns None instead of raising ValueError when entity not found."""
    dsmr_meter._get_entity_id_by_translation_key = MagicMock(
        side_effect=ValueError("Entity not found")
    )
    result = dsmr_meter._get_entity_id_for_phase_sensor(
        Phase.L1, cf.CONF_PHASE_SENSOR_PRODUCTION
    )
    assert result is None


def test_get_entity_state_for_phase_sensor_missing_entity(dsmr_meter):
    """Returns None when entity_id lookup returns None."""
    dsmr_meter._get_entity_id_for_phase_sensor = MagicMock(return_value=None)
    dsmr_meter._get_entity_state = MagicMock()
    result = dsmr_meter._get_entity_state_for_phase_sensor(
        Phase.L1, cf.CONF_PHASE_SENSOR_PRODUCTION
    )
    assert result is None
    dsmr_meter._get_entity_state.assert_not_called()


def test_get_tracking_entities(dsmr_meter):
    class Entity:
        def __init__(self, entity_id, translation_key):
            self.entity_id = entity_id
            self.translation_key = translation_key

    dsmr_meter.entities = [
        Entity("sensor.power_l1", "instantaneous_active_power_l1_positive"),
        Entity("sensor.voltage_l1", "instantaneous_voltage_l1"),
        Entity("sensor.other", "some_other_key"),
    ]
    result = dsmr_meter.get_tracking_entities()
    assert "sensor.power_l1" in result
    assert "sensor.voltage_l1" in result
    assert "sensor.other" not in result


def test_get_entity_map_for_phase_valid(dsmr_meter):
    for phase in [Phase.L1, Phase.L2, Phase.L3]:
        mapping = dsmr_meter._get_entity_map_for_phase(phase)
        assert isinstance(mapping, dict)


def test_get_entity_map_for_phase_invalid(dsmr_meter):
    with pytest.raises(ValueError):
        dsmr_meter._get_entity_map_for_phase("invalid_phase")
