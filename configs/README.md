# Configuration

- `swarm_default.json`: every tunable of `SwarmConfig` (tick = 1 s, cell = 1 m). Generated from `src/swarm/config.py`, which stays the source of truth.
- `edge_profiles.json`: the simulated edge profiles. Their slow-down factors are **assumptions**, not measurements; `deploy/edge/edge_benchmark.py` replaces them with real numbers.
- `scenarios/*.json`: fully expanded example scenarios (map, starts, orders, network, humans). The dashboard's scenario builder loads and saves this format.
