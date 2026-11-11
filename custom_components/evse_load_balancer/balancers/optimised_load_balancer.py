"""Optimised Load Balancer Algorithm."""

from time import time

from ..const import OvercurrentMode, Phase  # noqa: TID252
from .balancer import Balancer


class OptimisedLoadBalancer(Balancer):
    """
    Optimised variant of the default Load Balancer.

    This one is less aggressive in reducing and increasing the limits.
    It allows spikes to happen without immediate action, and is a bit
    more relaxed in increasing the limits again to prevent hysteresis.

    On the other hand, it does put a bit more load on your circuit, as it
    accepts temporary overcurrent situations, and only reduces the limits
    when the risk is high enough.
    """

    def __init__(
        self,
        max_limits: dict[Phase, int],
        trip_risk_threshold: int = 60,
        risk_decay_per_second: float = 1.0,
        overcurrent_mode: OvercurrentMode = OvercurrentMode.OPTIMISED,
    ) -> None:
        """Initialize the load balancer."""
        self._phase_monitors = {
            phase: PhaseMonitor(
                phase=phase,
                max_limit=max_limits[phase],
                trip_risk_threshold=trip_risk_threshold,
                risk_decay_per_second=risk_decay_per_second,
                overcurrent_mode=overcurrent_mode,
            )
            for phase in max_limits
        }

    def compute_availability(
        self,
        available_currents: dict[Phase, int],
        now: float | None = None,
    ) -> dict[Phase, int]:
        """
        Compute the current to hand out or take away per phase.

        Positive values can be handed out to chargers, negative values have
        to be taken away from them and zero means that nothing should change.
        """
        if now is None:
            now = time()
        available = {}
        for phase, current in available_currents.items():
            available[phase] = self._phase_monitors[phase].update(
                avail=current, now=now
            )
        return available


class PhaseMonitor:
    """Monitor a single phase."""

    def __init__(
        self,
        phase: Phase,
        max_limit: int,
        trip_risk_threshold: int = 60,
        risk_decay_per_second: float = 1.0,
        overcurrent_mode: OvercurrentMode = OvercurrentMode.OPTIMISED,
    ) -> None:
        """Monitor given phase current availability and return normalised limits."""
        self.phase = phase
        self.max_limit = max_limit
        self.phase_limit = max_limit
        self._trip_risk_threshold = trip_risk_threshold
        self._risk_decay_per_second = risk_decay_per_second
        self._overcurrent_mode = overcurrent_mode

        self._last_compute: float | None = None
        self._cumulative_trip_risk = 0.0

    def update(self, avail: float, now: float) -> float:
        """
        Return the current to hand out (positive) or take away (negative).

        Zero means "hold": there is no headroom, or an overcurrent is still
        being tolerated. A deficit is only reported on the cycle it has to be
        acted upon, so that a single overcurrent leads to a single reduction.
        """
        elapsed = now - self._last_compute if self._last_compute is not None else 0
        self._last_compute = now

        if avail >= 0:
            risk_decay = self._risk_decay_per_second * elapsed
            self._cumulative_trip_risk = max(
                0.0, self._cumulative_trip_risk - risk_decay
            )
            self.phase_limit = min(self.max_limit, avail)
            return self.phase_limit

        if self._overcurrent_mode == OvercurrentMode.OPTIMISED:
            self._cumulative_trip_risk += self._calculate_trip_risk(avail) * elapsed
            if self._cumulative_trip_risk < self._trip_risk_threshold:
                self.phase_limit = 0
                return self.phase_limit

        self._cumulative_trip_risk = 0.0
        self.phase_limit = avail
        return self.phase_limit

    def _calculate_trip_risk(self, available: float) -> float:
        """
        Calculate trip risk factor based on overcurrent percentage.

        Overcurrent percentage is a value between 0 and 1
        and the returned value is a fraction of the trip risk threshold
        devided by the number of seconds the overcurrency is allowed.
        the values here are roughly (as in extremely roughly) based on
        the trip risk curve in C-character circuit breakers.
        """
        if self.max_limit <= 0:
            return self._trip_risk_threshold
        overcurrent_percentage = abs(available) / self.max_limit
        if overcurrent_percentage <= 0.13:  # noqa: PLR2004
            return self._trip_risk_threshold / 60
        if overcurrent_percentage <= 0.40:  # noqa: PLR2004
            return self._trip_risk_threshold / 30
        if overcurrent_percentage <= 1.0:
            return self._trip_risk_threshold / 10
        return self._trip_risk_threshold
