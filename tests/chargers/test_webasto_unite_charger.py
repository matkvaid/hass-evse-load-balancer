"""Tests for the Webasto Unite charger implementation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.helpers.device_registry import DeviceEntry
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.evse_load_balancer.chargers.charger import PhaseMode
from custom_components.evse_load_balancer.chargers.webasto_unite_charger import (
    WebastoUniteCharger,
    WebastoUniteEntityMap,
    WebastoUniteStatusMap,
)
from custom_components.evse_load_balancer.const import (
    CHARGER_DOMAIN_WEBASTO_UNITE,
    Phase,
)


@pytest.fixture
def mock_hass():
    """Create a mock HomeAssistant instance for testing."""
    hass = MagicMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()
    return hass


@pytest.fixture
def mock_config_entry():
    """Create a mock ConfigEntry for the tests."""
    return MockConfigEntry(
        domain="evse_load_balancer",
        title="Webasto Unite Test Charger",
        data={"charger_type": "webasto_unite"},
        unique_id="test_webasto_unite_charger",
    )


@pytest.fixture
def mock_device_entry():
    """Create a mock DeviceEntry object for testing."""
    device_entry = MagicMock(spec=DeviceEntry)
    device_entry.id = "test_device_id"
    device_entry.identifiers = {("webasto_unite_modbus", "test_charger")}
    return device_entry


@pytest.fixture
def webasto_unite_charger(mock_hass, mock_config_entry, mock_device_entry):
    """Create a WebastoUniteCharger instance for testing."""
    with patch(
        "custom_components.evse_load_balancer.chargers.webasto_unite_charger.WebastoUniteCharger.refresh_entities"
    ):
        charger = WebastoUniteCharger(
            hass=mock_hass,
            config_entry=mock_config_entry,
            device_entry=mock_device_entry,
        )
        # Mock the _get_entity_state_by_key method
        charger._get_entity_state_by_key = MagicMock()
        # Mock the _get_entity_id_by_key method
        charger._get_entity_id_by_key = MagicMock(
            return_value="number.webasto_charging_current_limit"
        )
        return charger


def test_is_charger_device_true(mock_device_entry):
    """Test is_charger_device returns True for Webasto Unite devices."""
    mock_device_entry.identifiers = {(CHARGER_DOMAIN_WEBASTO_UNITE, "test_charger")}
    assert WebastoUniteCharger.is_charger_device(mock_device_entry) is True


def test_is_charger_device_false():
    """Test is_charger_device returns False for non-Webasto Unite devices."""
    device_entry = MagicMock(spec=DeviceEntry)
    device_entry.identifiers = {("other_domain", "test_charger")}
    assert WebastoUniteCharger.is_charger_device(device_entry) is False


async def test_set_current_limit(webasto_unite_charger, mock_hass):
    """Test setting current limits on the Webasto Unite charger."""
    # Setup test data
    test_limits = {
        Phase.L1: 16,
        Phase.L2: 14,
        Phase.L3: 15,
    }

    # Call the method
    await webasto_unite_charger.set_current_limit(test_limits)

    # Verify service call was made with correct parameters
    mock_hass.services.async_call.assert_called_once_with(
        domain="number",
        service="set_value",
        service_data={
            "entity_id": "number.webasto_charging_current_limit",
            "value": 14,  # Should use minimum of the values
        },
        blocking=True,
    )


def test_get_current_limit_success(webasto_unite_charger):
    """Test retrieving the current limit when entity exists."""
    # Mock the entity state
    webasto_unite_charger._get_entity_state_by_key.return_value = "16"

    # Call the method
    result = webasto_unite_charger.get_current_limit()
    assert result == {Phase.L1: 16, Phase.L2: 16, Phase.L3: 16}
    webasto_unite_charger._get_entity_state_by_key.assert_called_once_with(
        WebastoUniteEntityMap.DynamicChargerLimit
    )


def test_get_current_limit_none(webasto_unite_charger):
    """Test retrieving the current limit when entity is unavailable."""
    # Mock the entity state as None
    webasto_unite_charger._get_entity_state_by_key.return_value = None

    # Call the method
    result = webasto_unite_charger.get_current_limit()
    assert result is None


def test_get_max_current_limit_success(webasto_unite_charger):
    """Test retrieving the max current limit when entity exists."""
    # Mock the entity state
    webasto_unite_charger._get_entity_state_by_key.return_value = "32"

    # Call the method
    result = webasto_unite_charger.get_max_current_limit()
    assert result == {Phase.L1: 32, Phase.L2: 32, Phase.L3: 32}
    webasto_unite_charger._get_entity_state_by_key.assert_called_once_with(
        WebastoUniteEntityMap.MaxChargerLimit
    )


def test_get_max_current_limit_none(webasto_unite_charger):
    """Test retrieving the max current limit when entity is unavailable."""
    # Mock the entity state as None
    webasto_unite_charger._get_entity_state_by_key.return_value = None

    # Call the method
    result = webasto_unite_charger.get_max_current_limit()
    assert result is None


def test_car_connected_preparing(webasto_unite_charger):
    """Test car_connected returns True when charger is in preparing state."""
    webasto_unite_charger._get_entity_state_by_key.return_value = str(
        WebastoUniteStatusMap.Preparing
    )
    assert webasto_unite_charger.car_connected() is True


def test_car_connected_charging(webasto_unite_charger):
    """Test car_connected returns True when charger is charging."""
    webasto_unite_charger._get_entity_state_by_key.return_value = str(
        WebastoUniteStatusMap.Charging
    )
    assert webasto_unite_charger.car_connected() is True


def test_car_connected_suspended_evse(webasto_unite_charger):
    """Test car_connected returns True when charger is suspended by EVSE."""
    webasto_unite_charger._get_entity_state_by_key.return_value = str(
        WebastoUniteStatusMap.SuspendedEVSE
    )
    assert webasto_unite_charger.car_connected() is True


def test_car_connected_suspended_ev(webasto_unite_charger):
    """Test car_connected returns True when charger is suspended by EV."""
    webasto_unite_charger._get_entity_state_by_key.return_value = str(
        WebastoUniteStatusMap.SuspendedEV
    )
    assert webasto_unite_charger.car_connected() is True


def test_car_connected_finishing(webasto_unite_charger):
    """Test car_connected returns True when charger is finishing."""
    webasto_unite_charger._get_entity_state_by_key.return_value = str(
        WebastoUniteStatusMap.Finishing
    )
    assert webasto_unite_charger.car_connected() is True


def test_car_connected_available(webasto_unite_charger):
    """Test car_connected returns False when charger is available."""
    webasto_unite_charger._get_entity_state_by_key.return_value = str(
        WebastoUniteStatusMap.Available
    )
    assert webasto_unite_charger.car_connected() is False


def test_can_charge_preparing(webasto_unite_charger):
    """Test can_charge returns True when charger is preparing."""
    webasto_unite_charger._get_entity_state_by_key.return_value = str(
        WebastoUniteStatusMap.Preparing
    )
    assert webasto_unite_charger.can_charge() is True


def test_can_charge_charging(webasto_unite_charger):
    """Test can_charge returns True when charger is charging."""
    webasto_unite_charger._get_entity_state_by_key.return_value = str(
        WebastoUniteStatusMap.Charging
    )
    assert webasto_unite_charger.can_charge() is True


def test_can_charge_suspended_ev(webasto_unite_charger):
    """Test can_charge returns True when charger is suspended by EV."""
    webasto_unite_charger._get_entity_state_by_key.return_value = str(
        WebastoUniteStatusMap.SuspendedEV
    )
    assert webasto_unite_charger.can_charge() is True


def test_can_charge_suspended_evse(webasto_unite_charger):
    """Test can_charge returns False when charger is suspended by EVSE."""
    webasto_unite_charger._get_entity_state_by_key.return_value = str(
        WebastoUniteStatusMap.SuspendedEVSE
    )
    assert webasto_unite_charger.can_charge() is False


def test_is_charging_true(webasto_unite_charger):
    """Test is_charging returns True when charger is actively charging."""
    webasto_unite_charger._get_entity_state_by_key.return_value = str(
        WebastoUniteStatusMap.Charging
    )
    assert webasto_unite_charger.is_charging() is True


def test_is_charging_false(webasto_unite_charger):
    """Test is_charging returns False when charger is not charging."""
    webasto_unite_charger._get_entity_state_by_key.return_value = str(
        WebastoUniteStatusMap.Preparing
    )
    assert webasto_unite_charger.is_charging() is False


def test_has_synced_phase_limits(webasto_unite_charger):
    """Test has_synced_phase_limits returns True."""
    assert webasto_unite_charger.has_synced_phase_limits() is True


def test_set_phase_mode(webasto_unite_charger):
    """Test set_phase_mode does not raise an error."""
    # Should not raise an exception for valid modes
    webasto_unite_charger.set_phase_mode(PhaseMode.SINGLE)
    webasto_unite_charger.set_phase_mode(PhaseMode.MULTI)


def test_set_phase_mode_invalid(webasto_unite_charger):
    """Test set_phase_mode raises ValueError for invalid mode."""
    with pytest.raises(ValueError, match="Invalid mode"):
        webasto_unite_charger.set_phase_mode("invalid_mode")
