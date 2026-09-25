"""Configuration objects for the EdgeSwarm decentralized fleet engine.

Every tunable used by the engine lives here so that experiments are fully
reproducible from (config, seed).  One simulation tick = 1 s of robot time and
one grid cell = 1 m, so the nominal robot speed is 1 m/s.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# Coordination modes (ablation ladder, Phase 15)
STOP_AND_WAIT = "stop_and_wait"          # A: traditional baseline
DECENTRALIZED_ASTAR = "decentralized_astar"  # B: P2P intent sharing + reactive A* replanning
RESERVATION = "reservation"              # C: + space-time reservations, priority negotiation, deadlock probes
RESERVATION_AI = "reservation_ai"        # D: + predictive Edge-AI conflict intelligence
FULL = "full"                            # E: + resilient comms, energy/congestion auction, predictive rerouting

MODES = (STOP_AND_WAIT, DECENTRALIZED_ASTAR, RESERVATION, RESERVATION_AI, FULL)
MODE_LABELS = {
    STOP_AND_WAIT: "A. Stop-and-wait baseline",
    DECENTRALIZED_ASTAR: "B. Decentralized A* only",
    RESERVATION: "C. Decentralized + reservation",
    RESERVATION_AI: "D. + predictive Edge-AI",
    FULL: "E. Full EdgeSwarm",
}


@dataclass
class NetworkConfig:
    """Radio model.  All values are simulated, not measured on hardware."""

    range_cells: float = 8.0          # radio range (Euclidean, cells ~ metres)
    latency_ms: float = 40.0          # mean one-way latency
    jitter_ms: float = 20.0           # +/- uniform jitter
    packet_loss: float = 0.0          # independent per-receiver drop probability
    tick_ms: float = 1000.0           # tick duration used to convert latency -> ticks
    # Dead zones: list of (x0, y0, x1, y1, t_start, t_end) inclusive rectangles; a robot
    # inside an active dead zone can neither send nor receive.
    dead_zones: list[tuple[int, int, int, int, int, int]] = field(default_factory=list)
    # Global outage windows (t_start, t_end): nobody can communicate.
    outages: list[tuple[int, int]] = field(default_factory=list)
    # Individual radio failures: (robot_index, t_start, t_end)
    isolated_robots: list[tuple[int, int, int]] = field(default_factory=list)
    bandwidth_kbps: float = 2000.0    # per-robot uplink budget used for overhead reporting


@dataclass
class EdgeProfile:
    """Constrained-hardware emulation (Phase 12).  Simulated, see docs/ARCHITECTURE.md."""

    name: str = "simulation"
    enabled: bool = False
    # Measured decision time on the dev machine is multiplied by this factor to
    # estimate time on the target.  Factor is an assumption, documented.
    cpu_slowdown: float = 1.0
    decision_budget_ms: float = 200.0   # max compute per robot per tick before the robot must hold
    ram_budget_mb: float = 64.0
    max_message_bytes: int = 1400      # single UDP datagram payload budget


EDGE_PROFILES = {
    "simulation": EdgeProfile(),
    "raspberry_pi_4": EdgeProfile(name="raspberry_pi_4", enabled=True, cpu_slowdown=6.0,
                                  decision_budget_ms=200.0, ram_budget_mb=256.0),
    "jetson_nano": EdgeProfile(name="jetson_nano", enabled=True, cpu_slowdown=4.0,
                               decision_budget_ms=200.0, ram_budget_mb=512.0),
}


@dataclass
class SwarmConfig:
    mode: str = FULL
    seed: int = 1
    robots: int = 5
    tasks: int = 20
    scenario: str = "medium_congestion"
    max_ticks: int = 1500

    # Robot physics / tasks
    sensing_radius: int = 2            # onboard proximity sensing (lidar/UWB), Manhattan cells
    dwell_ticks: int = 2               # pickup / drop handling time
    move_energy: float = 0.12          # % battery per cell moved
    carry_energy: float = 0.04         # extra % per cell when loaded
    idle_energy: float = 0.01          # % per tick stationary
    low_battery: float = 25.0          # go-charge threshold
    charge_target: float = 90.0
    charge_rate: float = 3.0           # % per tick on dock
    reserve_battery: float = 12.0      # energy-aware allocation must keep this reserve

    # Planning
    st_horizon: int = 30               # space-time A* horizon (ticks)
    broadcast_path_len: int = 12       # cells of intent shared in each STATE message
    wait_timeout: int = 8              # stop-and-wait: replan after this many blocked ticks
    stale_drop_ticks: int = 2          # modes without resilience ignore beliefs older than this

    # Edge-AI (modes reservation_ai / full)
    ai_model_path: str = "models/conflict_model.json"
    ai_conflict_threshold: float = 0.5
    ai_deadlock_threshold: float = 0.5
    ai_reroute_margin: float = 1.0     # alternate route must beat expected cost by this many ticks
    ai_eval_radius: int = 6

    # Allocation weights (mode full); see docs/TASK_ALLOCATION.md
    w_distance: float = 1.0
    w_eta: float = 0.5
    w_congestion: float = 2.0
    w_conflict: float = 4.0
    w_energy: float = 10.0
    w_workload: float = 3.0
    w_priority: float = 2.0

    network: NetworkConfig = field(default_factory=NetworkConfig)
    edge: EdgeProfile = field(default_factory=EdgeProfile)

    # Scenario overrides (filled by scenario builder)
    scenario_params: dict[str, Any] = field(default_factory=dict)

    # Feature toggles derived from mode (can be overridden for experiments)
    def uses_reservations(self) -> bool:
        return self.mode in (RESERVATION, RESERVATION_AI, FULL)

    def uses_ai(self) -> bool:
        return self.mode in (RESERVATION_AI, FULL)

    def uses_resilience(self) -> bool:
        return self.mode == FULL

    def uses_smart_allocation(self) -> bool:
        return self.mode == FULL

    def uses_predictive_rerouting(self) -> bool:
        return self.mode == FULL

    def uses_p2p_intents(self) -> bool:
        return self.mode != STOP_AND_WAIT

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
