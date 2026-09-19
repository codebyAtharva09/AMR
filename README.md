# FleetOS — Decentralized AMR Fleet Coordination

SIH Problem Statement **26123** (Bharat Electronics Limited): decentralized coordination
and collision avoidance for a fleet of Autonomous Mobile Robots (AMRs) in a smart
warehouse, without a central server making per-robot decisions.

This repo is a full software simulation (no physical hardware) built to demonstrate the
approach convincingly: a Python simulation engine models the fleet's onboard control
logic, a React + Three.js dashboard visualizes it in real time, and a companion 3D
racking configurator (**Rack Studio**) generates the realistic warehouse racks both
tools render.

## Why this counts as decentralized

Every `AMRAgent` (`backend/app/simulation/agent.py`) only ever touches its **own**
fields plus whatever it received this tick over `MessageBus`
(`backend/app/simulation/comms.py`) — a range-limited broadcast channel standing in for
a real wireless mesh (WiFi mesh / UWB / BLE). No agent method ever reads another
agent's Python object directly, and there is no central class that computes fleet-wide
routing or assignment decisions. Concretely:

- **Collision avoidance** — each robot senses neighbors' broadcast (position,
  velocity, radius) within its own comm radius and independently computes a
  collision-free velocity (`orca.py`): an ORCA-inspired reciprocal velocity-obstacle
  correction for anticipated close approaches, layered with a potential-field
  repulsion as a robust safety floor. A final per-tick positional separation pass
  (`Simulation._resolve_overlaps`) acts as a bump-sensor-style backstop.
- **Deadlock resolution** — when stuck, an agent broadcasts which specific neighbor
  is blocking it (`deadlock.py`). Any agent can build the resulting Wait-For-Graph
  from these broadcasts and run **Tarjan's strongly-connected-components algorithm**
  locally to find real cycles (not just pairwise conflicts) — a genuine deadlock,
  not just contention. Every agent in a detected cycle then evaluates the same
  deterministic priority tuple `(task_priority, battery, -id)` and independently
  arrives at the same yielding agent, with no negotiation round and no coordinator.
  `backend/test_deadlock.py` proves this on an actual 3-robot rotational cycle.
- **Task allocation** — new pickup jobs are broadcast over the mesh
  (`task_allocation.py`). Every idle robot that hears the announcement computes its
  own bid (distance + battery penalty) and broadcasts it. Each robot then decides
  **locally**, from only the bids it itself received, whether it is the winner
  (lowest bid, numeric-id tie-break) — a decentralized contract-net auction, not a
  dispatcher assigning work. A won task is immediately marked `claimed` so it stops
  being re-broadcast and can't be double-claimed by a later idle robot.
- **Re-routing** — if a robot's current path crosses a newly blocked aisle, it
  re-runs A* on its own copy of the warehouse graph and continues; no coordinator
  reroutes it.
- **Battery awareness** — a robot diverts to the nearest charger when idle and low,
  and will also abandon a task mid-route (handing it back to the mesh as `pending`
  again) if its battery hits a critical floor before finishing, rather than running
  at 0% forever.

Because the decision logic is self-contained per agent, this same code could run
unchanged on separate Raspberry Pi / Jetson boards talking over real MQTT or UDP
broadcast instead of the in-process `MessageBus` — swapping the transport wouldn't
require touching `agent.py`, `orca.py`, or `task_allocation.py`.

## Success criteria (from the PS)

- **Zero inter-robot collisions** — verified in `backend/smoke_test.py`,
  `backend/stress_test.py`, and `backend/benchmark_suite.py` (which runs 4, 6, 9,
  15, and 30-agent fleets for 1,000–10,000 ticks each, with 0–8 blocked-aisle
  events): **0 collisions in every single run**, including the 30-agent/10,000-tick
  case (completes in ~78s wall time).
- **≥20% faster task completion vs. stop-and-wait** — the engine runs a same-schedule
  "shadow" simulation of a naive stop-and-wait baseline (full stop whenever a
  higher-priority neighbor is approaching) alongside the visualized fleet, so the
  dashboard's metrics panel shows a live, fair comparison. Real measured results
  from `benchmark_suite.py`: **+46.4% (6 agents), +69.0% (9 agents), +32.1% (15
  agents), +59.6% (30 agents)**. The 4-agent/0-blockage case measured −1.9%
  (essentially flat) — with almost no path contention at that size, the
  coordination protocol has nothing to improve on; that's an honest result, not a
  cherry-picked one, and it's consistent with "improvement scales with density."

## What's been built so far

**Backend simulation (Python/FastAPI)**
- Full decentralized agent loop: ORCA-style avoidance, contract-net-style task
  auction, A* re-routing, battery drain/charging, and real Tarjan SCC-based
  Wait-For-Graph deadlock resolution (`deadlock.py`).
- Two parallel fleets ticked every step (visualized "primary" + same-schedule
  "shadow") so the dashboard can show a live, fair mode comparison.
- REST + WebSocket API: block/unblock a specific aisle, unblock all, add/remove a
  robot, reset the fleet to 5 robots, switch mode, live snapshot stream at 15Hz.
- Headless verification: `smoke_test.py`, `stress_test.py`, `benchmark_suite.py`
  (4/6/9/15/30-agent scenarios matching the pitch deck's benchmark table with real
  numbers), and `test_deadlock.py` (proves the WFG mechanism resolves an actual
  3-robot rotational cycle, not just pairwise contention).

**Fleet dashboard (React + Three.js)**
- Real-time animated warehouse view: robots with battery rings, state labels,
  velocity-based heading, pulsing comm-link lines between nearby robots (the P2P
  mesh, visualized), pending-task markers, blocked-aisle markers.
- Realistic procedural racking (see Rack Studio below) rendered directly in the
  fleet view — grouped from the warehouse's per-cell rack layout into proper
  shelving rows, not flat boxes.
- Fleet Control panel: mode toggle, per-aisle block/clear, **Deploy Robot / Remove
  Robot / Reset Fleet**, live fleet-size readout.
- Metrics panel with a live bar-chart comparison, mesh-traffic event feed showing
  bid/claim auction messages as they happen.

**Rack Studio (`frontend/src/rack-configurator/`)** — a standalone 3D warehouse
racking visualizer/configurator, opened via the "Rack Studio" button in the top bar:
- Three procedurally-built rack types (no external `.gltf` assets): **Selective**
  (ladder-frame uprights, punched-hole steel texture, diagonal cross-bracing, step
  beams with safety pins, wire-mesh/flush-steel/wood-panel/open-frame decking),
  **Cantilever** (columns + base beams, angled arms, pipe bundles / lumber stacks),
  **Drive-In** (deep nested lanes, continuous rails, top/rear bracing, floor guide
  rails).
- Parametric controls: rack type, bay count, tier count, bay width/depth/clearance
  (mm + ft), decking type, cargo toggle + density + variant, 3 color themes.
- 5 camera presets (isometric/front/top-down/side/walkthrough) with smooth
  transitions, hover tooltips and click-to-inspect on structural members
  (dimensions + max load), a live stats HUD (weight capacity, pallet slots,
  footprint, bill of materials), and JSON/PNG export.

## Bugs found and fixed

A self-review pass caught several real issues, all fixed and re-verified:

| Issue | Fix |
|---|---|
| Task double-claim: a won task was never marked non-pending, so a later idle robot could re-bid and claim it again — inflating throughput and corrupting the completion-time average | Task now flips to `"claimed"` immediately on a won bid |
| Robots visually teleported instead of moving smoothly | The animated group's position is no longer a reactive JSX prop fighting the `useFrame` lerp — it's set once on mount, then purely lerp-driven |
| One uncaught exception in the simulation tick would freeze the whole demo silently | Tick loop now catches and logs exceptions, keeps serving the last good snapshot |
| Clicking "Clear" on one blocked aisle cleared *every* blocked aisle | Added a real per-aisle unblock endpoint |
| Agent-ID priority/tie-break logic compared IDs as strings (`"AMR-10" < "AMR-2"`), scrambling ordering past 9 robots | All tie-breaks now use a numeric sort key |
| A robot whose battery hit 0% mid-task just kept driving forever | Battery-critical check now applies during active tasks too — the robot abandons the task (handing it back to the mesh) and diverts to the nearest charger |
| No way to remove robots after deploying several, or reset the demo | Added Remove Robot and Reset Fleet controls |
| Rack Studio's footprint stat ignored drive-in racking's actual 3x nested lane depth | Fixed to match the visual lane depth |
| Fleet dashboard rendered racks as one flat box per grid cell (54 boxes, no structure) | Replaced with grouped, realistic shelving rows using the same procedural technique as Rack Studio |
| Pitch document claimed "Tarjan WFG deadlock detection" was already built; the code only had a simple stuck-timer + nearest-neighbor heuristic | Actually implemented: `deadlock.py` builds the Wait-For-Graph and runs real Tarjan SCC, proven on a genuine 3-robot cycle in `test_deadlock.py` |
| Pitch document's benchmark table and several citations (an IEEE Access DOI, a "Bischoff 2021 IROS" paper, a "Bhatt 2023 ICRA" paper) were never produced/verified | Ran the real 4/6/9/15/30-agent benchmarks (`benchmark_suite.py`) and web-verified every citation; unverifiable ones were removed rather than kept — see `FleetOS_Complete_Master.md` Sections 10, 13, 22 |

## Architecture

```
backend/                       Python simulation + FastAPI/WebSocket server
  app/simulation/
    warehouse.py                Grid layout (racks, aisles, stations) + nav graph
    pathfinding.py               A* routing, re-run on blocked-edge detection
    orca.py                      Per-agent collision-avoidance velocity computation
    comms.py                     Range-limited broadcast bus (mesh stand-in)
    task_allocation.py           Decentralized contract-net-style auction
    deadlock.py                  Wait-For-Graph + Tarjan SCC deadlock resolution
    agent.py                     AMRAgent: the onboard control loop
    engine.py                    Ticks the fleet, spawns tasks, scenario events
    metrics.py                   Collision counting, completion-time tracking
  app/main.py                    FastAPI app: REST controls + WebSocket stream
  smoke_test.py / stress_test.py /
  benchmark_suite.py / test_deadlock.py   Headless verification runs

frontend/                      React + TypeScript + Vite dashboard
  src/components/
    WarehouseScene.tsx           Three.js scene: floor, racks, stations, camera
    RealisticRack.tsx            Procedural shelving rows for the fleet view
    RobotMesh.tsx                Animated robot with battery ring + state label
    CommLinks.tsx                Pulsing lines visualizing the P2P mesh
    BlockedAisleMarkers.tsx      Red markers at blocked intersections
    TaskMarkers.tsx               Pulsing markers for pending/in-flight tasks
    ControlPanel.tsx             Mode toggle, per-aisle block/clear, deploy/remove/reset
    FleetRoster.tsx / MetricsPanel.tsx / EventFeed.tsx   Sidebar panels
  src/hooks/useSimulationSocket.ts   WebSocket client with auto-reconnect
  src/store/useFleetStore.ts         Zustand store

  src/rack-configurator/         Standalone "Rack Studio" 3D configurator
    components/3d/                SelectiveRack, CantileverRack, DriveInRack,
                                   RackParts, PalletCargo, WarehouseFloor, CameraRig
    components/ui/                ConfigPanel, StatsHUD, HoverTooltip, InspectModal
    store/useRackConfigStore.ts    Zustand store for the configurator's own state
    utils/                        textures.ts (procedural canvas textures), bom.ts,
                                   exportConfig.ts
```

## Running it

**Backend** (Python 3.11+):

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate   # or source .venv/bin/activate on Linux/Mac
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Headless verification (no server needed):

```bash
python smoke_test.py     # ~5min sim, block/unblock event, prints comparison
python stress_test.py    # larger fleet, multiple blockages, longer run
```

**Frontend** (Node 18+):

```bash
cd frontend
npm install
npm run dev
```

Open the printed `http://localhost:5173` URL. The dashboard connects to the backend's
WebSocket at `ws://127.0.0.1:8000/ws`. Click **Rack Studio** in the top bar to open the
standalone racking configurator (no backend connection needed for that view).

> Note: editing backend source doesn't affect an already-running `uvicorn` process —
> restart it to pick up changes. The frontend Vite dev server hot-reloads automatically.

## Demo script

1. Let the fleet run for ~30s in Decentralized ORCA mode — point out the comm-link
   lines pulsing between nearby robots (that's the mesh, not a server), the realistic
   racking, and the event feed showing bid/claim traffic for task auctions.
2. Click a "Block Aisle" button — watch robots re-route live, red markers appear at
   the blocked intersection. Click "Clear" to reopen just that one aisle.
3. Switch to Stop-and-Wait mode — same fleet, same task schedule, visibly slower;
   the metrics panel's bar chart and "speed advantage" stat make the ≥20%
   improvement obvious.
4. Deploy a few extra robots to show the auction/task allocation scaling live, then
   use Remove Robot / Reset Fleet to show the fleet size is fully controllable.
5. Open **Rack Studio**, switch between Selective / Cantilever / Drive-In, hover and
   click a structural member for its spec sheet, and export a PNG or JSON config.
