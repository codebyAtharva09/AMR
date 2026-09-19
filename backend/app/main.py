import asyncio
import json
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .models import BlockAisleRequest, SetModeRequest
from .simulation.engine import DEFAULT_NUM_AGENTS, FleetEngine
from .simulation.warehouse import COLS, ROWS, RACK_ROWS, RACK_COLS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fleetos")

app = FastAPI(title="AMR Fleet Coordination Simulation")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = FleetEngine(num_agents=DEFAULT_NUM_AGENTS)
TICK_HZ = 15
_latest_snapshot: dict = {}


async def _simulation_loop():
    global _latest_snapshot
    while True:
        try:
            engine.tick()
            _latest_snapshot = engine.snapshot()
        except Exception:
            # Never let one bad tick kill the loop - log it, keep serving the last
            # good snapshot, and try again next tick instead of freezing the demo.
            logger.exception("simulation tick failed - continuing with last good snapshot")
        await asyncio.sleep(1 / TICK_HZ)


@app.on_event("startup")
async def _start_loop():
    asyncio.create_task(_simulation_loop())


@app.get("/api/layout")
def get_layout():
    racks = [
        {"row": r, "col": c}
        for r in range(ROWS)
        for c in range(COLS)
        if r in RACK_ROWS and c in RACK_COLS
    ]
    return {
        "rows": ROWS,
        "cols": COLS,
        "cell_size": engine.primary.warehouse.cell_size,
        "racks": racks,
        "pickup_stations": engine.primary.warehouse.pickup_stations,
        "dropoff_stations": engine.primary.warehouse.dropoff_stations,
        "charging_stations": engine.primary.warehouse.charging_stations,
    }


@app.post("/api/block_aisle")
def block_aisle(req: BlockAisleRequest):
    engine.block_aisle(req.row, req.col)
    return {"ok": True}


@app.post("/api/unblock_aisle")
def unblock_aisle(req: BlockAisleRequest):
    engine.unblock_aisle(req.row, req.col)
    return {"ok": True}


@app.post("/api/unblock_all")
def unblock_all():
    engine.unblock_all()
    return {"ok": True}


@app.post("/api/add_agent")
def add_agent():
    engine.add_agent()
    return {"ok": True, "count": len(engine.primary.agents)}


@app.post("/api/remove_agent")
def remove_agent():
    removed = engine.remove_agent()
    return {"ok": removed, "count": len(engine.primary.agents)}


@app.post("/api/reset")
def reset():
    global _latest_snapshot
    engine.reset()
    _latest_snapshot = engine.snapshot()
    return {"ok": True, "count": len(engine.primary.agents)}


@app.post("/api/set_mode")
def set_mode(req: SetModeRequest):
    engine.set_mode(req.mode)
    return {"ok": True}


@app.get("/api/snapshot")
def snapshot():
    return _latest_snapshot or engine.snapshot()


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            if _latest_snapshot:
                await websocket.send_text(json.dumps(_latest_snapshot))
            await asyncio.sleep(1 / TICK_HZ)
    except WebSocketDisconnect:
        pass
