"""Webasto Unite Charger implementation."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from ..const import CHARGER_DOMAIN_WEBASTO_UNITE, Phase  # noqa: TID252
from ..ha_device import HaDevice  # noqa: TID252
from .charger import Charger, PhaseMode

_LOGGER = logging.getLogger(__name__)


class WebastoUniteEntityMap:
    """
    Map Webasto Unite entities to their respective attributes.

    https://github.com/matkvaid/webasto_unite_modbus/blob/main/custom_components/webasto_unite_modbus/sensor.py
    https://github.com/matkvaid/webasto_unite_modbus/blob/main/custom_components/webasto_unite_modbus/number.py
    """

    Status = "charge_point_state"
    DynamicChargerLimit = "charging_current_limit"
    MaxChargerLimit = "evse_max_current"


class WebastoUniteStatusMap:
    """
    Map Webasto Unite charger statuses to their respective string representations.

    States based on OCPP charge point state values:
    @see https://github.com/matkvaid/webasto_unite_modbus/blob/main/custom_components/webasto_unite_modbus/coordinator.py
    """

    Available = 0  # Charger is available for a new session
    Preparing = 1  # Charger is preparing to start charging
    Charging = 2  # Charger is actively charging
    SuspendedEVSE = 3  # Charging suspended by EVSE
    SuspendedEV = 4  # Charging suspended by EV
    Finishing = 5  # Charging session is finishing
    Reserved = 6  # Charger is reserved
    Unavailable = 7  # Charger is unavailable
    Faulted = 8  # Charger has a fault


class WebastoUniteCharger(HaDevice, Charger):
    """Implementation of the Charger class for Webasto Unite chargers."""

    def __init__(
        self, hass: HomeAssistant, config_entry: ConfigEntry, device_entry: DeviceEntry
    ) -> None:
        """Initialize the Webasto Unite charger."""
        HaDevice.__init__(self, hass, device_entry)
        Charger.__init__(self, hass, config_entry, device_entry)
        self.refresh_entities()

    @staticmethod
    def is_charger_device(device: DeviceEntry) -> bool:
        """Check if the given device is a Webasto Unite charger."""
        return any(
            id_domain == CHARGER_DOMAIN_WEBASTO_UNITE
            for id_domain, _ in device.identifiers
        )

    async def async_setup(self) -> None:
        """Set up the charger."""

    def set_phase_mode(self, mode: PhaseMode, _phase: Phase | None = None) -> None:
        """Set the phase mode of the charger."""
        if mode not in PhaseMode:
            msg = "Invalid mode. Must be 'single' or 'multi'."
            raise ValueError(msg)
        # Webasto Unite does not support dynamic phase mode switching
        # Phase configuration is determined by hardware installation

    async def set_current_limit(self, limit: dict[Phase, int]) -> None:
        """
        Set the current limit for the charger.

        As Webasto Unite only supports setting the current limit for all phases,
        we'll use the lowest value from the provided limits.
        """
        # Get the entity_id for the charging_current_limit number entity
        dynamic_limit_entity_id = self._get_entity_id_by_key(
            WebastoUniteEntityMap.DynamicChargerLimit
        )

        value = min(limit.values())

        # Call the Home Assistant number.set_value service
        await self.hass.services.async_call(
            domain="number",
            service="set_value",
            service_data={
                "entity_id": dynamic_limit_entity_id,
                "value": value,
            },
            blocking=True,
        )

    def get_current_limit(self) -> dict[Phase, int] | None:
        """Get the current limit of the charger in amps."""
        state = self._get_entity_state_by_key(
            WebastoUniteEntityMap.DynamicChargerLimit
        )
        if state is None:
            _LOGGER.warning(
                "Current limit not available. "
                "Make sure the required entity (%s) is enabled.",
                WebastoUniteEntityMap.DynamicChargerLimit,
            )
            return None

        try:
            current_limit = int(float(state))
        except (ValueError, TypeError):
            _LOGGER.warning(
                "Could not parse current limit value: %s",
                state,
            )
            return None

        return dict.fromkeys(Phase, current_limit)

    def get_max_current_limit(self) -> dict[Phase, int] | None:
        """Return maximum configured current for the charger."""
        state = self._get_entity_state_by_key(WebastoUniteEntityMap.MaxChargerLimit)
        if state is None:
            _LOGGER.warning(
                "Max charger limit not available. "
                "Make sure the required entity (%s) is enabled.",
                WebastoUniteEntityMap.MaxChargerLimit,
            )
            return None

        try:
            max_limit = int(float(state))
        except (ValueError, TypeError):
            _LOGGER.warning(
                "Could not parse max current limit value: %s",
                state,
            )
            return None

        return dict.fromkeys(Phase, max_limit)

    def has_synced_phase_limits(self) -> bool:
        """
        Return whether the charger has synced phase limits.

        Webasto Unite applies the same current limit to all phases.
        """
        return True

    def _get_status(self) -> int | None:
        """Get the current charge point state."""
        state = self._get_entity_state_by_key(WebastoUniteEntityMap.Status)
        if state is None:
            return None

        try:
            return int(float(state))
        except (ValueError, TypeError):
            _LOGGER.warning(
                "Could not parse charge point state value: %s",
                state,
            )
            return None

    def car_connected(self) -> bool:
        """Check if a car is connected to the charger."""
        status = self._get_status()
        return status in [
            WebastoUniteStatusMap.Preparing,
            WebastoUniteStatusMap.Charging,
            WebastoUniteStatusMap.SuspendedEVSE,
            WebastoUniteStatusMap.SuspendedEV,
            WebastoUniteStatusMap.Finishing,
        ]

    def can_charge(self) -> bool:
        """Check if the charger is ready to deliver charge."""
        status = self._get_status()
        return status in [
            WebastoUniteStatusMap.Preparing,
            WebastoUniteStatusMap.Charging,
            WebastoUniteStatusMap.SuspendedEV,
        ]

    def is_charging(self) -> bool:
        """Check if the charger is actively charging."""
        status = self._get_status()
        return status == WebastoUniteStatusMap.Charging

    async def async_unload(self) -> None:
        """Unload the Webasto Unite charger."""
