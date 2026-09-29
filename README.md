# Smart Industrial Warehouse — Decentralized Autonomous AMR Fleet Coordination

[![Tests](https://img.shields.io/badge/pytest-161%20passing-brightgreen.svg)]()
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)]()
[![Architecture](https://img.shields.io/badge/Architecture-Decentralized%20P2P%20Mesh-orange.svg)]()

A high-performance, decentralized coordination platform for Autonomous Mobile Robot (AMR) fleets operating in smart industrial warehouses. Designed to eliminate single points of failure inherent to centralized fleet dispatchers, this platform empowers every AMR as an independent edge computing node utilizing peer-to-peer (P2P) mesh communication, spatio-temporal reservation tables, dynamic negotiation protocols, and directed Wait-For-Graph (WFG) deadlock resolution.

Includes the **3D Fleet Command Center** (Three.js digital twin, served locally, works offline) with a 7-scene guided demo.

## EdgeSwarm: predictive, resilient, energy-aware decentralized coordination (SIH26123)

![EdgeSwarm 3D Fleet Command Center (simulation)](presentation_assets/demo/edgeswarm_demo.gif)

**Demo video (40 s):** [`presentation_assets/demo/EdgeSwarm_demo.mp4`](presentation_assets/demo/EdgeSwarm_demo.mp4). It is a
simulation recording with 10 AMRs, 15% message loss, humans, a blocked aisle and a Wi-Fi dead zone.
Judge prep: [`docs/JUDGE_QA.md`](docs/JUDGE_QA.md). Repository: https://github.com/codebyAtharva09/AMR

Every AMR runs its own copy of the coordinator (`src/swarm/agent.py`) using only its sensors and radio messages.
The radio drops, delays and loses messages; a ground-truth monitor counts every collision.

**Measured in simulation** (10 scenarios × 3/5/10/15 AMRs × 30 seeds, `experiments/results/benchmark_summary.json`):

| | Stop-and-wait baseline | EdgeSwarm (full) |
|---|---|---|
| Inter-robot collisions (1200 runs each) | 0 | **0** |
| Mean makespan | 217.5 ticks | **163.1 ticks (−25.0%)** |
| Cells with ≥20% reduction | – | 21 / 40 (all 10- and 15-AMR cells; not at 3 AMRs, most 5-AMR cells) |

**Versus a central fleet server** (same planner, perfect Wi-Fi, `experiments/central_outage.py`, 300 runs): tied with no
disruption (central 0–2% ahead, within noise). During a 60 s Wi-Fi/server outage the central fleet freezes (about 1 order delivered)
while EdgeSwarm keeps delivering 10–23 orders and finishes 18–21% sooner. There were 0 collisions.

The main gain comes from space-time reservations; the Edge-AI conflict predictor adds little on top (see ablation in
`docs/EXPERIMENT_RESULTS.md`). No physical-robot tests have been done.

```bash
pip install -r requirements.txt
python3 main.py --mode dashboard            # then open /command-center (3D Fleet Command Center, 7-scene demo)
python3 main.py --mode edge-demo            # same demo headless
python3 main.py --mode swarm --scenario high_congestion --robots 10 --seed 3
python3 main.py --mode swarm-benchmark --quick
python3 main.py --mode ablation --quick
python3 main.py --mode train-ai
python3 main.py --mode deadlock-suite
python3 main.py --mode distributed --robots 5   # one OS process per robot, messages over UDP
pytest -q
```

Docs: [ARCHITECTURE](docs/ARCHITECTURE.md) · [EDGE_AI](docs/EDGE_AI.md) ·
[COMMUNICATION_RESILIENCE](docs/COMMUNICATION_RESILIENCE.md) · [TASK_ALLOCATION](docs/TASK_ALLOCATION.md) ·
[DEADLOCK_HANDLING](docs/DEADLOCK_HANDLING.md) · [BENCHMARK_METHODOLOGY](docs/BENCHMARK_METHODOLOGY.md) ·
[EXPERIMENT_RESULTS](docs/EXPERIMENT_RESULTS.md) · [LIMITATIONS](docs/LIMITATIONS.md) · [NOVELTY](docs/NOVELTY.md) ·
[DEMO_SCRIPT](docs/DEMO_SCRIPT.md) · [FINAL_READINESS](docs/FINAL_READINESS.md)

The original simulator below is kept unchanged as the baseline (`--mode demo / dashboard / benchmark`).

---

---

## Table of Contents

- [Key Capabilities](#key-capabilities)
- [System Architecture](#system-architecture)
- [Industrial Warehouse Model & Physics](#industrial-warehouse-model--physics)
- [Decentralized Coordination Engine](#decentralized-coordination-engine)
- [Autonomous Energy & Charging Lifecycle](#autonomous-energy--charging-lifecycle)
- [Interactive 3D Digital Twin & Dashboard](#interactive-3d-digital-twin--dashboard)
- [12 Industrial Scenarios](#12-industrial-scenarios)
- [Installation & Setup](#installation--setup)
- [Usage & Running](#usage--running)
- [Testing & Validation](#testing--validation)
- [Benchmark Results](#benchmark-results)
- [Repository Layout](#repository-layout)

---

## Key Capabilities

- **Decentralized P2P Mesh Coordination**: No central dispatch server. AMRs broadcast state and local spatial intents within a configurable communication radius (8 cells), resolving headway conflicts autonomously.
- **Multi-Factor Priority Bidding**: Dynamic peer negotiation protocol evaluates cargo payload status, task priority (1–5), battery reserve, remaining distance, and charging urgency to award right-of-way.
- **Spatio-Temporal Reservation Tables**: 4D vertex reservations `(x, y, t)` and edge-swap reservations `(u, v, t)` completely eliminate head-on swapping and cell-occupancy collisions before execution.
- **Directed WFG Deadlock Resolution**: Real-time cycle detection identifies circular wait dependencies; conceding AMRs safely execute single-step corridor evacuations and perimeter detours.
- **Authoritative Hard Rack Obstacles**: 24 physical industrial storage racks (small, medium, large, multi-tier) strictly enforced across A* search, collision detection, movement physics, and task generation. Zero rack ghosting or corner cutting.
- **Per-AMR Battery Governance**: Individual battery tracking (<35% trigger). Low-battery AMRs safely complete atomic steps, route through walkable aisles to available charging docks, charge for **exactly 5 seconds** (5 simulation ticks) to 100.0% full capacity, and resume assigned work queues without halting other fleet members.
- **Live Speed Scaling**: Global (0.1x – 5.0x) and per-AMR speed adjustment updates velocity live while preserving AMR identity, coordinates, active routes, and task queues without resets or teleportation.
- **ISO 3691-4-inspired Safety Supervisor** (not certified): Enforces dynamic RESTRICTED, CAUTION, and CLEAR safety zones around hazards, triggering automated corridor clearing and safety stops.
- **Comprehensive Analytics & Export**: Live Chart.js telemetry (makespan, throughput, message overhead, conflict mitigation) and automated multi-tab Excel workbook generation.

---

## System Architecture

```mermaid
flowchart TD
    subgraph Fleet ["Decentralized AMR Fleet (Edge Nodes)"]
        AMR1["AMR-001 (Node)"] <-->|P2P Mesh| AMR2["AMR-002 (Node)"]
        AMR2 <-->|P2P Mesh| AMR3["AMR-003 (Node)"]
        AMR3 <-->|P2P Mesh| AMR1
    end

    subgraph CoreEngine ["On-Robot Planning & Coordination"]
        ASTAR["A* Spatial Planner"]
        RES["Spatio-Temporal Reservation Table"]
        NEG["Negotiation Protocol (Bidding)"]
        WFG["Wait-For-Graph Cycle Breaker"]
        BAT["Battery Safety Governor"]
    end

    subgraph Environment ["Physical Warehouse Domain"]
        MAP["Warehouse Grid (20x23)"]
        RACKS["24 Physical Storage Racks"]
        DOCKS["Autonomous Charging Docks"]
        SAFETY["ISO 3691-4 Safety Supervisor"]
    end

    subgraph Telemetry ["Monitoring & Operations"]
        DASH["Fleet Command Center (Port 8000)"]
        TWIN["Three.js 3D Digital Twin"]
        EXCEL["Automated Excel KPI Exporter"]
    end

    Fleet --> CoreEngine
    CoreEngine --> Environment
    CoreEngine --> DASH
    DASH --> TWIN
    CoreEngine --> EXCEL
```

---

## Industrial Warehouse Model & Physics

The authoritative warehouse representation (`src/warehouse/warehouse.py`) models an expanded **20 × 23** industrial logistics facility:

- **Perimeter & Structural Walls**: Bounded by non-walkable outer security perimeters.
- **24 Industrial Storage Racks**: Categorized into `small` (2x1, 2 tiers), `medium` (3x1/4x1, 3 tiers), and `large` (6x1, 4 tiers) horizontal racks positioned across rows `y=2, 5, 8, 11, 14, 17`.
- **Authoritative Rack Cells**: All 83 coordinates occupied by physical racks are treated as hard grid obstacles across all system layers.
- **Single-Step Orthogonal Motion**: Movement is strictly constrained to orthogonal steps (`abs(dx) + abs(dy) == 1`). Diagonal movement and corner-cutting through rack corners are strictly forbidden.
- **Dedicated Infrastructure**: Designated corner charging stations (e.g. `(1, 18)`, `(18, 18)`) and structured fleet home bays.

---

## Decentralized Coordination Engine

### 1. Peer-to-Peer Communication (`src/coordination/peer_network.py`)
- Emulates ad-hoc IEEE 802.11p / 5G-NR Sidelink communication.
- Operates within an 8-cell radio frequency range.
- Incorporates configurable channel noise, message latency, and packet loss modeling.

### 2. Priority Bidding Protocol (`src/coordination/conflict_resolution.py`)
When two AMRs attempt to claim the same transit waypoint or approach head-on in an aisle:
$$\text{Bid} = 100.0 \cdot \mathbb{I}_{\text{carrying}} + 20.0 \cdot \text{Priority} + 0.1 \cdot \text{Battery} - 0.5 \cdot \text{DistToGoal} + \text{ChargingBonus}$$
The winning AMR maintains right-of-way; the yielding AMR replans an alternate route or executes a safe single-step evacuation.

### 3. Spatio-Temporal Reservations (`src/planning/reservation_table.py`)
- **Vertex Reservation**: Guarantees no two AMRs occupy `(x, y)` at timestamp `t`.
- **Edge Reservation**: Guarantees no two AMRs traverse `(u, v)` and `(v, u)` at timestamp `t`, preventing edge-swapping head-on collisions.

### 4. Wait-For-Graph Cycle Resolution (`src/simulation/simulator.py`)
Directed dependency graph tracking which AMR is waiting on which peer. When a cycle (deadlock) forms:
1. Operational scores evaluate the lowest-impact AMR in the cycle.
2. The conceding AMR steps into an adjacent free buffer cell (`_move_robot(conceding, evac_cell)`).
3. The conflict zone is cleared, unlocking the remaining fleet members.

---

## Autonomous Energy & Charging Lifecycle

```
[ Normal Delivery Task ]
          │
          ▼
   Battery < 35.0%
          │
          ▼
[ Finish Step Safely ] ──► [ Plan Path to Available Dock ]
                                      │
                                      ▼
                      [ Transit Through Valid Aisles ]
                                      │
                                      ▼
                      [ Arrive at Charging Dock ]
                                      │
                                      ▼
                      [ Docked Session: Exactly 5s ]
                        (Battery restored to 100.0%)
                                      │
                                      ▼
                      [ Release Dock Reservation ]
                                      │
                                      ▼
                      [ Resume Work Queue / Next Task ]
```

- **Per-AMR Isolation**: Charging is an individual AMR property. An AMR entering charging **never** pauses or freezes the rest of the fleet.
- **Physical Transit**: AMRs physically drive through collision-free warehouse grid cells to corner docks. No instant teleportation or ghosting.
- **Dock Duration**: Exactly 5 seconds (5 simulation ticks) at the charging station to reach 100.0% full capacity.
- **Queue & Dock Contention**: If both corner stations are occupied, incoming low-battery AMRs safely wait in a dynamic queue while other delivery operations proceed unimpeded.

---

## Interactive 3D Digital Twin & Dashboard

The browser front end is the **Fleet Command Center** at `/command-center`. `/` redirects there.
- Live 3D twin: differential-drive AMRs, tote transfers, LiDAR and safety fields, workers, dead zones, AI risk arcs.
- A 2D view, Start / Pause / Step / Reset controls, speed control, day and night themes.
- Fleet, AI-calls, Robot ("why this task?"), Shift-log, Scenario, Builder and Results tabs.
- A 7-scene guided SIH demo.

The older "classic" dashboard has been removed.

---

## 12 Industrial Scenarios

The simulator includes 12 automated scenarios (`src/simulation/scenarios.py`):

| # | Scenario ID | Description |
| :-: | :--- | :--- |
| **1** | `head_on_conflict` | Two AMRs face each other in a narrow aisle; loaded AMR wins priority bid while empty AMR yields. |
| **2** | `dynamic_obstacle` | Injects an unexpected obstacle into active transit; triggers instant route invalidation and A* rerouting. |
| **3** | `narrow_aisle` | High-traffic single-lane aisle contention testing reservation headway and passing bays. |
| **4** | `deadlock_cycle` | 4 AMRs enter a 4-way circular intersection lock; resolved by WFG directed cycle breaker. |
| **5** | `charger_outage` | Primary charger failure; low-battery AMRs dynamically divert to secondary corner docks. |
| **6** | `restricted_zone` | ISO 3691-4 dynamic restricted safety perimeter declared; instant corridor evacuation and perimeter detour. |
| **7** | `cross_dock_rush` | High-volume logistics surge; dynamic lane balancing and throughput preservation. |
| **8** | `low_battery_cascade` | Simultaneous low-battery events across multiple AMRs; tests dock queueing and fleet independence. |
| **9** | `motor_stall_recovery` | AMR motor fault simulation; cargo automatically reassigned to nearest idle peer. |
| **10** | `sensor_degradation` | Partial sensor failure triggering cautious speed derating and expanded safety margins. |
| **11** | `high_density_expansion` | 20 AMRs concurrently operating across 100 tasks testing high-density corridor traffic. |
| **12** | `multi_domain_disruption` | Simultaneous corridor blockage, drive motor stall, and primary charger outage testing resilience. |

---

## Installation & Setup

### Prerequisites
- Python 3.10+ (tested on Python 3.10, 3.11, 3.12, 3.13, 3.14)
- Modern web browser (Chrome, Safari, Firefox, Edge) with WebGL support

### Setup Virtual Environment
```bash
# Clone the repository
git clone https://github.com/codebyAtharva09/AMR.git
cd AMR

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

---

## Usage & Running

### 1. Launch 3D Digital Twin & Web Dashboard
```bash
python3 main.py --mode dashboard
```
*Or directly via the server entry point:*
```bash
python3 -m src.visualization.dashboard_server
```
Open **`http://127.0.0.1:8000/command-center`** in your browser (`/` redirects there).

### 2. Run Headless Simulation Demo
```bash
python3 main.py --mode demo --robots 5 --tasks 20 --steps 50
```

### 3. Run Benchmark Suite
Compares decentralized coordination against baseline stop-and-wait strategies across multiple random seeds:
```bash
python3 main.py --mode benchmark --robots 5 --tasks 20 --steps 60
```

---

## Testing & Validation

The codebase includes an extensive automated test suite covering all modules:

```bash
# Run all 109 automated tests
pytest -v
```

### Targeted Fix Test Suite (`tests/test_final_targeted_fixes.py`)
Directly verifies the core operational requirements:
```bash
pytest tests/test_final_targeted_fixes.py -v
```
- `test_test1_single_low_battery`: Single AMR <35% enters charging, other 4 continue, reaches dock, charges for exactly 5s to 100.0%, resumes tasks.
- `test_test2_multiple_low_battery`: Multiple AMRs <35% enter charging simultaneously, dock contention handled cleanly, zero fleet pause.
- `test_test3_speed_change_live`: Speed updated live (1.0x to 2.0x); position, identity, route, task queue, and battery preserved with zero jumps.
- `test_test4_rack_collision_hard_obstacles`: Verified A* rejects rack cells, physical move engine blocks rack penetration, 0 fleet rack penetrations over execution.
- `test_test5_long_workload_5_10_20`: Verified 5 AMRs, 10 AMRs, and 20 AMRs complete 100/100 tasks without fleet stalls or freezes.

---

## Benchmark Results

The table that used to be here (819/491/285 ticks) had no reproducible experiment behind it; see `docs/audit/AUDIT_REPORT.md`.
Measured results for the legacy simulator are in `docs/baseline_results.md`; results for EdgeSwarm are in
[`docs/EXPERIMENT_RESULTS.md`](docs/EXPERIMENT_RESULTS.md).

---

## Repository Layout

The repository is organised by deployment stage: **source → tests → experiments/evidence → deployment → docs**.

```
.
├── main.py                     # single CLI: demo | dashboard | swarm | distributed | swarm-benchmark | ablation | ...
├── pyproject.toml, Makefile    # packaging (`pip install -e .` → `edgeswarm` command) and `make test|dashboard|experiments`
├── requirements.txt            # runtime deps (operator PC); robot-side deps are in deploy/edge/
├── configs/                    # swarm_default.json, edge_profiles.json, scenarios/*.json (scenario builder saves here)
├── src/
│   ├── swarm/                  # ★ EdgeSwarm core: agent (per-robot brain), safety gate, belief/comm states,
│   │                           #   space-time planner, radio model, world + ground-truth monitor, distributed runtime
│   ├── edge_ai/                # conflict/deadlock predictor: features, training, NumPy-only inference
│   ├── baselines/              # published comparison planners (PIBT, central, perfect information)
│   ├── command_center/         # controller + 7-scene demo behind the 3D dashboard
│   ├── visualization/          # HTTP server + Three.js 3D Command Center (static/)
│   └── simulation/, warehouse/, planning/, coordination/, ...   # original (legacy) prototype, kept working
├── models/                     # trained Edge-AI model (255 KB JSON) + training report
├── tests/                      # 161 pytest tests + tests/e2e (Playwright browser test)
├── experiments/                # one script per experiment; results/*.json = every number in the deck
├── deploy/
│   ├── docker/                 # Dockerfile.server (dashboard), Dockerfile.edge (arm64 robot image), docker-compose.yml
│   ├── edge/                   # edge_benchmark.py (time the loop on a Pi/Jetson), requirements-edge.txt, systemd unit
│   └── ros2/                   # RobotState.msg + topic/QoS mapping for the ROS 2 node
├── docs/                       # architecture, safety proof, experiment results, limitations, judge Q&A, readiness
│   └── audit/                  # audit of the original repository
├── presentation_assets/        # figures + demo video (figure_sources.json maps each figure to its data)
├── datasets/dedicat6g/         # DEDICAT 6G warehouse robot KPI logs (sensitivity inputs, not benchmark inputs)
├── notebooks/                  # the team's original Colab prototype
└── archive/                    # superseded scratch scripts and legacy browser tests (not run in CI)
```

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
