"""Custom Meter leveraging existing sensors."""

import logging
from math import floor

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from .. import config_flow as cf  # noqa: TID252
from .meter import Meter, Phase

_LOGGER = logging.getLogger(__name__)

PHASE_CONF_MAP: dict[Phase, str] = {
    Phase.L1: cf.CONF_PHASE_KEY_ONE,
    Phase.L2: cf.CONF_PHASE_KEY_TWO,
    Phase.L3: cf.CONF_PHASE_KEY_THREE,
}


class CustomMeter(Meter):
    """Customer Meter implementation of the Meter class."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the Custom Meter instance."""
        Meter.__init__(self, hass, config_entry)
        self._config_entry_data = config_entry.data

    def get_active_phase_current(self, phase: Phase) -> int | None:
        """Return available current on a given phase."""
        phase_config = self._config_entry_data.get(PHASE_CONF_MAP[phase], None)
        if phase_config is None:
            return None

        active_power = self.get_active_phase_power(phase)
        voltage_state = self._get_state(phase_config[cf.CONF_PHASE_SENSOR_VOLTAGE])
        if None in [active_power, voltage_state]:
            _LOGGER.debug(
                "Missing states for phase %s: active_power: %s, voltage_state: %s. "
                "Are the entities enabled?",
                phase,
                active_power,
                voltage_state,
            )
            return None
        return floor((active_power * 1000) / voltage_state) if voltage_state else None

    def get_active_phase_power(self, phase: Phase) -> float | None:
        """Return the active power on a given phase."""
        phase_config = self._config_entry_data[PHASE_CONF_MAP[phase]]
        consumption = self._get_state(phase_config[cf.CONF_PHASE_SENSOR_CONSUMPTION])
        production = self._get_state(phase_config[cf.CONF_PHASE_SENSOR_PRODUCTION])
        if None in [consumption, production]:
            _LOGGER.debug(
                "Missing states for phase %s: consumption: %s, production: %s. "
                "Are the entities enabled?",
                phase,
                consumption,
                production,
            )
            return None
        return consumption - production

    def get_tracking_entities(self) -> list[str]:
        """Return a list of entity IDs that should be tracked for this meter."""
        sensors = []
        for phase_cf in PHASE_CONF_MAP.values():
            # Only the phases that are in use have been configured
            phase_config = self._config_entry_data.get(phase_cf)
            if phase_config is None:
                continue
            sensors.extend(
                phase_config[cf_sensor]
                for cf_sensor in (
                    cf.CONF_PHASE_SENSOR_CONSUMPTION,
                    cf.CONF_PHASE_SENSOR_PRODUCTION,
                    cf.CONF_PHASE_SENSOR_VOLTAGE,
                )
            )
        return sensors

    def _get_state(self, entity_id: str) -> float | None:
        state = self.hass.states.get(entity_id)
        if state is None:
            _LOGGER.debug("State not found for entity %s", entity_id)
            return None
        state_value = state.state
        if state_value in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            _LOGGER.debug("Entity %s has no value: %s", entity_id, state_value)
            return None
        try:
            return float(state_value)
        except ValueError:
            _LOGGER.debug(
                "Failed to parse state %s for entity %s", state_value, entity_id
            )
            return None
