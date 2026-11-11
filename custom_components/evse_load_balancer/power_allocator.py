"""PowerAllocator for managing charger power allocation."""

import logging
from math import floor
from time import time

from .chargers.charger import Charger
from .const import Phase

_LOGGER = logging.getLogger(__name__)

# Number of settle times to wait for a meter reading that is new enough to show
# the effect of a reduction, before that reduction is no longer accounted for.
MAX_SETTLE_FACTOR = 4


class ChargerState:
    """Tracks internal allocation state for a single charger."""

    def __init__(self, charger: Charger) -> None:
        """Initialize charger state."""
        self.charger = charger
        self.requested_current: dict[Phase, int] | None = None
        self.last_calculated_current: dict[Phase, int] | None = None
        self.last_calculated_base: dict[Phase, int] | None = None
        self.last_applied_current: dict[Phase, int] | None = None
        self.previous_applied_current: dict[Phase, int] | None = None
        self.pending_reduction: dict[Phase, int] = {}
        self.pending_reduction_time: float | None = None
        self.last_update_time: int = 0
        self.manual_override_detected: bool = False
        self.initialized: bool = False
        self._active_session: bool = False

    def initialize(self) -> bool:
        """Initialize with current charger settings."""
        if self.initialized:
            _LOGGER.debug("Charger %s already initialized", self.charger.id)
            return True

        current_limits = self.charger.get_current_limit()
        if current_limits:
            self.requested_current = dict(current_limits)
            self.last_applied_current = dict(current_limits)
            self._active_session = self.charger.can_charge()
            if self._active_session:
                # During a session the limit on the charger may be one we lowered
                # ourselves before a restart or reload. Adopting it as the
                # requested current would make that reduction permanent, so
                # request the maximum, just like at the start of a session.
                max_limits = self.charger.get_max_current_limit()
                if max_limits:
                    self.requested_current = dict(max_limits)
            _LOGGER.info("Charger initialized with limits: %s", current_limits)
            self.initialized = True
            return True

        _LOGGER.debug("Could not initialize charger - no current limits available")
        return False

    def detect_manual_override(self) -> None:
        """Detect and take care of manual override implications."""
        current_setting = self.get_current_limit()

        if not current_setting:
            return

        is_charging = self.charger.can_charge()

        if is_charging and not self._active_session:
            max_limits = self.charger.get_max_current_limit()
            if max_limits:
                self.requested_current = dict(max_limits)
                _LOGGER.info(
                    "New charging session detected for %s, resetting to maximum: %s",
                    self.charger.id,
                    max_limits,
                )
                self._active_session = True

        # Check if current differs from what we last set
        elif (
            self.last_applied_current
            and current_setting
            and any(
                current_setting[phase] != self.last_applied_current[phase]
                for phase in current_setting
            )
            # A slow-polling charger (e.g. Modbus) can still report the value
            # from before our latest command once the settle time has passed.
            # That looks identical to a manual override unless we also check
            # it isn't simply an unconfirmed echo of our own requested or
            # previously applied current.
            and current_setting
            not in (self.requested_current, self.previous_applied_current)
        ):
            self.requested_current = dict(current_setting)
            self.manual_override_detected = True
            _LOGGER.info(
                "Manual override detected for charger. New requested current: %s",
                current_setting,
            )

        # Always set active_session
        self._active_session = is_charging

    def get_current_limit(self) -> dict[Phase, int] | None:
        """Get the current limit of the charger."""
        if (
            int(time()) - self.last_update_time
            < self.charger.current_change_settle_time
        ):
            return self.last_applied_current

        return self.charger.get_current_limit()

    def add_pending_reduction(
        self, reduction: dict[Phase, int], timestamp: float
    ) -> None:
        """Remember a reduction that the meter readings do not reflect yet."""
        for phase, amps in reduction.items():
            self.pending_reduction[phase] = self.pending_reduction.get(phase, 0) + amps
        self.pending_reduction_time = timestamp

    def clear_pending_reduction(self, phase: Phase | None = None) -> None:
        """Forget the pending reduction for one phase, or for all of them."""
        if phase is None:
            self.pending_reduction.clear()
        else:
            self.pending_reduction.pop(phase, None)
        if not self.pending_reduction:
            self.pending_reduction_time = None

    def expire_pending_reduction(self, now: float, measured_at: float | None) -> None:
        """
        Forget reductions that the meter readings should reflect by now.

        When it is known at what time the meter last reported, a reduction is
        kept until a reading arrives that is new enough to contain its effect.
        That keeps slowly reporting meters from triggering the same cut twice.
        """
        if self.pending_reduction_time is None:
            return

        settle_time = self.charger.current_change_settle_time
        age = now - self.pending_reduction_time
        if measured_at is None:
            settled = age >= settle_time
        else:
            settled = (
                measured_at - self.pending_reduction_time >= settle_time
                or age >= settle_time * MAX_SETTLE_FACTOR
            )
        if settled:
            self.clear_pending_reduction()


class PowerAllocator:
    """
    Manages power allocation to multiple EV chargers based on available current.

    Responsibilities:
    - Track original requested currents for each charger
    - Distribute available power among chargers using selected strategy
    - Reduce charger power when available current is negative
    - Restore charger power when more current is available
    - Handle manual overrides by users

    All without actually updating the chargers, which is done in the coordinator.
    """

    def __init__(self) -> None:
        """Initialize the power allocator."""
        self._chargers: dict[str, ChargerState] = {}

    def add_charger(self, charger: Charger) -> bool:
        """
        Add a charger to be managed by the allocator.

        Returns True if added successfully, False if charger already exists
        """
        charger_id = charger.id
        if charger_id in self._chargers:
            _LOGGER.warning("Charger %s already exists in PowerAllocator", charger_id)
            return False

        charger_state = ChargerState(charger)
        self._chargers[charger_id] = charger_state
        _LOGGER.info("Added charger %s to PowerAllocator", charger_id)

        return True

    def add_charger_and_initialize(self, charger: Charger) -> bool:
        """Add charger and immediately initialize."""
        if self.add_charger(charger):
            return self._chargers[charger.id].initialize()
        return False

    def remove_charger(self, charger: Charger) -> bool:
        """Remove a charger from the allocator."""
        charger_id = charger.id
        if charger_id in self._chargers:
            del self._chargers[charger_id]
            _LOGGER.info("Removed charger %s from PowerAllocator", charger_id)
            return True
        return False

    @property
    def _active_chargers(self) -> dict[str, ChargerState]:
        """Return a dictionary of chargers that can take a charge."""
        return {
            charger_id: state
            for charger_id, state in self._chargers.items()
            if state.charger.can_charge()
        }

    def should_monitor(self) -> bool:
        """Check if any charger is connected and should be monitored."""
        return len(self._active_chargers) > 0

    def update_allocation(
        self,
        available_currents: dict[Phase, int],
        now: float | None = None,
        measured_at: float | None = None,
    ) -> dict[str, dict[Phase, int]]:
        """
        Update power allocation for all chargers based on available current.

        Args:
            available_currents: Current to hand out (positive) or to take away
                (negative) per phase.
            now: Timestamp of this cycle, defaults to the current time.
            measured_at: Timestamp at which the meter last reported, if known.

        Returns:
            Dict mapping charger_id to new current limits (empty if no updates)

        """
        if not self._active_chargers:
            return {}

        if now is None:
            now = time()

        # Check for initialized chargers and manual overrides
        for state in self._chargers.values():
            if not state.initialized and not state.initialize():
                continue

            state.detect_manual_override()
            state.expire_pending_reduction(now, measured_at)

        # Allocate current based on strategy
        allocated_currents = self._allocate_current(available_currents)

        # Create result dictionary for chargers that need updating
        result = {}
        for charger_id, new_limits in allocated_currents.items():
            state = self._chargers[charger_id]
            current_setting = state.get_current_limit()

            if not current_setting:
                continue

            # Check if update is needed
            has_changes = False
            if state.charger.has_synced_phase_limits():
                min_current = min(current_setting.values())
                min_new = min(new_limits.values()) if new_limits else min_current
                has_changes = min_new != min_current
            else:
                has_changes = any(
                    new_limits[phase] != current_setting[phase] for phase in new_limits
                )

            if has_changes:
                result[charger_id] = new_limits
                state.last_calculated_current = dict(new_limits)
                state.last_calculated_base = dict(current_setting)
                state.manual_override_detected = False

        return result

    def update_applied_current(
        self, charger_id: str, applied_current: dict[Phase, int], timestamp: int
    ) -> None:
        """Update the record of what current was actually applied to the charger."""
        if charger_id not in self._chargers:
            _LOGGER.warning("Charger %s not found in PowerAllocator", charger_id)
            return

        state = self._chargers[charger_id]

        # The limits the applied ones were calculated from. Not read from the
        # charger, as it may already report the limits that are being applied.
        base_current = state.last_calculated_base or state.last_applied_current or {}
        reduction = {
            phase: base_current[phase] - limit
            for phase, limit in applied_current.items()
            if limit < base_current.get(phase, limit)
        }
        if reduction:
            state.add_pending_reduction(reduction, timestamp)
        else:
            state.clear_pending_reduction()

        state.previous_applied_current = state.last_applied_current
        state.last_applied_current = dict(applied_current)
        state.last_update_time = timestamp
        _LOGGER.debug(
            "Updated applied current for charger %s: %s", charger_id, applied_current
        )

    def _allocate_current(
        self, available_currents: dict[Phase, int]
    ) -> dict[str, dict[Phase, int]]:
        """
        Allocate current proportionally to requested currents.

        For negative available current (overcurrent), distribute cuts proportionally.
        For positive available current, distribute increases proportionally.

        Returns a dictionary mapping charger_id to new current limits.
        """
        result: dict[str, dict[Phase, int]] = {}

        # Handle overcurrent and recovery separately for each phase
        for phase, available_current in available_currents.items():
            if available_current < 0:
                # Overcurrent situation - distribute cuts proportionally
                self._distribute_cuts(phase, available_current, result)
            elif available_current > 0:
                # Headroom shows that earlier reductions have taken effect
                for state in self._chargers.values():
                    state.clear_pending_reduction(phase)
                # Recovery situation - distribute increases proportionally
                self._distribute_increases(phase, available_current, result)

        # Grab phases that should be processed
        processed_phases = set(available_currents.keys())

        # Flatten synced chargers which expect the current to be equal
        # across all phases
        for charger_id, charger_currents in result.items():
            state = self._active_chargers[charger_id]
            if state.charger.has_synced_phase_limits():
                # For synced chargers, use the minimum of the updated phases,
                # but only consider phases that were actually processed
                processed_currents = {
                    phase: current
                    for phase, current in charger_currents.items()
                    if phase in processed_phases
                }

                if processed_currents:
                    min_current = min(processed_currents.values())
                    result[charger_id] = dict.fromkeys(Phase, min_current)
                else:
                    # If no phases were processed, keep the original values
                    pass

        return result

    def _distribute_cuts(
        self, phase: Phase, deficit: int, result: dict[str, dict[Phase, int]]
    ) -> None:
        """Distribute current cuts proportionally during overcurrent."""
        # A reduction takes a while to show up in the meter readings. Until then
        # the readings still contain the overcurrent it was meant to resolve, so
        # cutting for the full deficit again would lower the chargers too far.
        deficit += sum(
            state.pending_reduction.get(phase, 0)
            for state in self._active_chargers.values()
        )
        if deficit >= 0:
            return

        charger_currents = []
        total_current = 0

        # Collect current settings for active chargers
        for charger_id, state in self._active_chargers.items():
            current_setting = state.get_current_limit()
            if not current_setting:
                continue

            current = current_setting[phase]
            charger_currents.append((charger_id, current))
            total_current += current

        if total_current == 0:
            return  # No active chargers or all at minimum

        # Calculate cuts proportionally
        for charger_id, current in charger_currents:
            # Calculate proportional cut based on current usage
            proportion = current / total_current
            cut = floor(deficit * proportion)

            state = self._chargers[charger_id]
            current_setting = state.get_current_limit()

            if charger_id not in result:
                result[charger_id] = current_setting.copy()

            result[charger_id][phase] = max(0, current_setting[phase] + int(cut))

    def _distribute_increases(
        self, phase: Phase, surplus: int, result: dict[str, dict[Phase, int]]
    ) -> None:
        """Distribute current increases proportionally during recovery."""
        potential_increases = []
        total_potential = 0

        # Calculate potential increases for each charger
        for charger_id, state in self._active_chargers.items():
            current_setting = state.get_current_limit()
            if not current_setting or not state.requested_current:
                continue

            current = current_setting[phase]
            requested = state.requested_current[phase]

            if requested > current:
                potential = requested - current
                potential_increases.append((charger_id, potential))
                total_potential += potential

        if total_potential == 0:
            return  # No potential increases

        # Calculate increases proportionally
        for charger_id, potential in potential_increases:
            proportion = potential / total_potential
            increase = min(surplus * proportion, potential)

            state = self._chargers[charger_id]
            current_setting = state.get_current_limit()

            if charger_id not in result:
                result[charger_id] = current_setting.copy()

            result[charger_id][phase] = current_setting[phase] + int(increase)
