"""End-to-end tests that run the integration inside Home Assistant."""

import logging
from datetime import timedelta

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.evse_load_balancer import logbook
from custom_components.evse_load_balancer import options_flow as of
from custom_components.evse_load_balancer.const import (
    CHARGER_DOMAIN_WEBASTO_UNITE,
    COORDINATOR_STATE_AWAITING_CHARGER,
    COORDINATOR_STATE_MONITORING_LOAD,
    DOMAIN,
    EVSE_LOAD_BALANCER_COORDINATOR_EVENT,
)

FUSE_SIZE = 25
CHARGER_MAX = 16
# With 250 V every whole amp is a power that floats represent exactly
VOLTAGE = 250

STATE_SENSOR = "sensor.evse_load_balancer_load_balancing_state"
CONSUMPTION_SENSOR = "sensor.l1_consumption"


class Home:
    """A house with a charger, a car and a meter that measures both."""

    def __init__(self, hass) -> None:
        """Initialize the house."""
        self.hass = hass
        self.house_load = 5
        self.limit = CHARGER_MAX
        self.limit_calls: list[int] = []
        self.entity_ids: dict[str, str] = {}

    def set_house_load(self, amps: int) -> None:
        """Change what the rest of the house consumes."""
        self.house_load = amps
        self.report_meter()

    def report_meter(self) -> None:
        """Let the meter report the load of the house and the car."""
        car = self.limit if self.limit >= 6 else 0
        self.hass.states.async_set(
            CONSUMPTION_SENSOR, str((self.house_load + car) * VOLTAGE / 1000)
        )

    async def handle_set_value(self, call) -> None:
        """Act as the charger receiving a new current limit."""
        self.limit = int(call.data["value"])
        self.limit_calls.append(self.limit)
        self.hass.states.async_set(call.data["entity_id"], str(float(self.limit)))
        self.report_meter()


@pytest.fixture
async def home(hass) -> Home:
    """Set up a Webasto Unite charger and the sensors of a custom meter."""
    home = Home(hass)

    charger_entry = MockConfigEntry(domain=CHARGER_DOMAIN_WEBASTO_UNITE)
    charger_entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=charger_entry.entry_id,
        identifiers={(CHARGER_DOMAIN_WEBASTO_UNITE, "SERIAL123")},
        manufacturer="Webasto",
        model="Unite",
        name="Webasto Unite",
    )
    home.entity_ids["device"] = device.id

    entity_registry = er.async_get(hass)
    for domain, key, state in (
        ("sensor", "charge_point_state", "Charging"),
        ("number", "charging_current_limit", str(float(CHARGER_MAX))),
        ("sensor", "evse_max_current", str(CHARGER_MAX)),
    ):
        entity = entity_registry.async_get_or_create(
            domain,
            CHARGER_DOMAIN_WEBASTO_UNITE,
            f"{charger_entry.entry_id}_{key}",
            config_entry=charger_entry,
            device_id=device.id,
        )
        home.entity_ids[key] = entity.entity_id
        hass.states.async_set(entity.entity_id, state)

    hass.services.async_register("number", "set_value", home.handle_set_value)

    hass.states.async_set("sensor.l1_production", "0")
    hass.states.async_set("sensor.l1_voltage", str(VOLTAGE))
    home.report_meter()
    return home


async def setup_load_balancer(hass, home: Home, **options) -> MockConfigEntry:
    """Set up the load balancer for the charger with a custom meter."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="EVSE Load Balancer",
        data={
            "charger_device": home.entity_ids["device"],
            "fuse_size": float(FUSE_SIZE),
            "phase_count": 1.0,
            "custom_phase_config": True,
            "l1": {
                "power_consumption": CONSUMPTION_SENSOR,
                "power_production": "sensor.l1_production",
                "voltage": "sensor.l1_voltage",
            },
        },
        options=options,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def integration_warnings(caplog) -> list[logging.LogRecord]:
    """Return the warnings and errors that the integration itself has logged."""
    return [
        record
        for record in caplog.records
        if record.levelno >= logging.WARNING
        and record.name.startswith("custom_components.evse_load_balancer")
    ]


async def run_cycles(hass, freezer, seconds: int) -> None:
    """Let the given number of one second balancing cycles pass."""
    for _ in range(seconds):
        freezer.tick(timedelta(seconds=1))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()


async def test_setup_and_unload(hass, freezer, home):
    """Test that the entry sets up its sensors and unloads cleanly."""
    entry = await setup_load_balancer(hass, home)
    assert entry.state is ConfigEntryState.LOADED

    await run_cycles(hass, freezer, 2)
    assert hass.states.get(STATE_SENSOR).state == COORDINATOR_STATE_MONITORING_LOAD
    assert home.limit_calls == []

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_overcurrent_is_reduced_once_and_restored(hass, freezer, home):
    """Test a single reduction for an overcurrent and the recovery after it."""
    await setup_load_balancer(
        hass, home, **{of.OPTION_CHARGE_LIMIT_HYSTERESIS: 1}
    )
    await run_cycles(hass, freezer, 5)

    # 15 A in the house + 16 A for the car is 6 A more than the fuse allows
    home.set_house_load(15)
    await run_cycles(hass, freezer, 25)
    assert home.limit_calls == [], "a short overcurrent has to be tolerated"

    await run_cycles(hass, freezer, 30)
    assert home.limit_calls == [10]

    home.set_house_load(5)
    await run_cycles(hass, freezer, 90)
    assert home.limit_calls == [10, 16]


async def test_overcurrent_is_reduced_immediately_in_strict_mode(hass, freezer, home):
    """Test that disabling temporary overcurrent reduces the charger right away."""
    await setup_load_balancer(
        hass, home, **{of.OPTION_ALLOW_TEMPORARY_OVERCURRENT: False}
    )
    await run_cycles(hass, freezer, 5)

    home.set_house_load(15)
    await run_cycles(hass, freezer, 3)
    assert home.limit_calls == [10]

    await run_cycles(hass, freezer, 60)
    assert home.limit_calls == [10]


async def test_restart_during_reduction_restores_the_limit(hass, freezer, home):
    """Test that a limit lowered before a restart is raised again afterwards."""
    home.limit = 6
    hass.states.async_set(home.entity_ids["charging_current_limit"], "6.0")
    home.report_meter()

    await setup_load_balancer(hass, home)
    await run_cycles(hass, freezer, 3)

    assert home.limit_calls == [CHARGER_MAX]


async def test_no_deprecated_home_assistant_api_is_used(hass, freezer, home, caplog):
    """Test that Home Assistant does not report usage of deprecated APIs."""
    entry = await setup_load_balancer(
        hass, home, **{of.OPTION_ALLOW_TEMPORARY_OVERCURRENT: False}
    )
    home.set_house_load(15)
    await run_cycles(hass, freezer, 5)
    assert home.limit_calls == [10]

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    # Home Assistant reports the use of deprecated APIs by integrations this way
    reports = [
        record.getMessage()
        for record in caplog.records
        if "Detected that custom integration" in record.getMessage()
    ]
    assert reports == []


async def test_limit_change_is_described_in_logbook(hass, freezer, home):
    """Test that the event of a new limit results in a readable logbook entry."""
    events = []
    hass.bus.async_listen(EVSE_LOAD_BALANCER_COORDINATOR_EVENT, events.append)
    await setup_load_balancer(
        hass, home, **{of.OPTION_ALLOW_TEMPORARY_OVERCURRENT: False}
    )

    home.set_house_load(15)
    await run_cycles(hass, freezer, 3)
    assert len(events) == 1

    describers = {}
    logbook.async_describe_events(
        hass, lambda domain, event_type, describe: describers.update({event_type: describe})
    )
    entry = describers[EVSE_LOAD_BALANCER_COORDINATOR_EVENT](events[0])

    assert entry["message"] == "charger limits set to: L1: 10A, L2: 10A, L3: 10A"


async def test_unavailable_charger_is_not_balanced(hass, freezer, home, caplog):
    """Test that an unavailable charger is waited for without flooding the log."""
    await setup_load_balancer(hass, home)
    caplog.clear()

    hass.states.async_set(home.entity_ids["charge_point_state"], STATE_UNAVAILABLE)
    home.set_house_load(25)
    await run_cycles(hass, freezer, 60)

    assert hass.states.get(STATE_SENSOR).state == COORDINATOR_STATE_AWAITING_CHARGER
    assert home.limit_calls == []
    assert integration_warnings(caplog) == []


async def test_missing_meter_reading_is_reported_once(hass, freezer, home, caplog):
    """Test that a meter without readings pauses balancing and is logged once."""
    await setup_load_balancer(
        hass, home, **{of.OPTION_ALLOW_TEMPORARY_OVERCURRENT: False}
    )
    await run_cycles(hass, freezer, 2)
    caplog.clear()

    hass.states.async_set(CONSUMPTION_SENSOR, STATE_UNAVAILABLE)
    await run_cycles(hass, freezer, 30)

    warnings = integration_warnings(caplog)
    assert len(warnings) == 1
    assert "No meter reading for phase 'l1'" in warnings[0].getMessage()

    # Balancing picks up again as soon as the meter is back
    home.set_house_load(15)
    await run_cycles(hass, freezer, 3)
    assert home.limit_calls == [10]
    assert "Meter readings are back" in caplog.text
