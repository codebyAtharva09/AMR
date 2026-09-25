"""Fleet Command Center controller: runs one EdgeSwarm simulation behind the dashboard.

The controller is only a *viewer and scenario driver*: it steps the simulation,
injects disruptions the operator asks for, and serialises snapshots.  It never
makes coordination decisions for the robots.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from src.swarm.config import EDGE_PROFILES, FULL, MODE_LABELS, MODES, SwarmConfig
from src.swarm.engine import SwarmSimulation
from src.swarm.scenarios import (BENCHMARK_SCENARIOS, DEADLOCK_SCENARIOS, DESCRIPTIONS, PRESETS, build_scenario,
                                 from_dict, list_custom, load_custom, save_custom)

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "experiments" / "results"


class SwarmController:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.running = False
        self.tick_interval = 0.35
        self.mode = FULL
        self.scenario = "medium_congestion"
        self.robots = 5
        self.seed = 7
        self.edge_profile = "simulation"
        self.custom: dict | None = None
        self.demo = None
        self.message = ""
        self.sim: SwarmSimulation | None = None
        self._last_snapshot: dict | None = None
        self.reset()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------ lifecycle
    def _make_cfg(self) -> SwarmConfig:
        cfg = SwarmConfig(mode=self.mode, seed=self.seed, robots=self.robots, tasks=4 * self.robots, scenario=self.scenario)
        cfg.edge = EDGE_PROFILES.get(self.edge_profile, EDGE_PROFILES["simulation"])
        return cfg

    def reset(self) -> None:
        with self.lock:
            cfg = self._make_cfg()
            try:
                if self.custom is not None:
                    spec = from_dict(self.custom)
                    cfg.robots = len(spec.starts)
                else:
                    spec = build_scenario(self.scenario, self.robots, 4 * self.robots, self.seed)
                self.sim = SwarmSimulation(cfg, spec)
                self.message = f"Loaded {spec.name} ({len(spec.starts)} AMRs, {len(spec.tasks)} tasks, seed {self.seed}, mode {self.mode})"
            except FileNotFoundError as exc:
                # AI model missing: fall back to the reservation mode and say so
                self.mode = "reservation"
                cfg = self._make_cfg()
                spec = build_scenario(self.scenario, self.robots, 4 * self.robots, self.seed)
                self.sim = SwarmSimulation(cfg, spec)
                self.message = f"{exc}; running mode 'reservation' instead"
            self.running = False
            self._last_snapshot = None

    def _loop(self) -> None:
        while True:
            time.sleep(self.tick_interval)
            with self.lock:
                if not self.running or self.sim is None:
                    continue
                if self.sim.finished_tick is not None and (self.demo is None or not self.demo.active):
                    self.running = False
                    continue
                if self.sim.tick >= self.sim.cfg.max_ticks:
                    self.running = False
                    continue
                self.sim.step()
                if self.demo is not None and self.demo.active:
                    self.demo.on_tick(self)
                self._last_snapshot = None

    # ------------------------------------------------------------------ state
    def state(self) -> dict[str, Any]:
        with self.lock:
            if self._last_snapshot is None and self.sim is not None:
                snap = self.sim.snapshot()
                snap["running"] = self.running
                snap["controller"] = {
                    "mode": self.mode, "mode_label": MODE_LABELS.get(self.mode, self.mode), "scenario": self.scenario,
                    "robots": len(self.sim.agents), "seed": self.seed, "tick_interval": self.tick_interval,
                    "edge_profile": self.edge_profile, "message": self.message,
                    "custom": self.custom is not None,
                }
                snap["demo"] = self.demo.status() if self.demo is not None else None
                snap["ai_model"] = self._ai_info()
                self._last_snapshot = snap
            return self._last_snapshot or {}

    def _ai_info(self) -> dict | None:
        ai = self.sim.ai if self.sim else None
        if ai is None:
            return None
        return {"conflict_model": ai.meta.get("conflict_model"), "deadlock_model": ai.meta.get("deadlock_model"),
                "conflict_threshold": ai.conflict_threshold, "deadlock_threshold": ai.deadlock_threshold,
                "size_bytes": ai.size_bytes(), "latency": ai.latency_stats()}

    def catalog(self) -> dict[str, Any]:
        return {
            "modes": [{"id": m, "label": MODE_LABELS[m]} for m in MODES],
            "presets": [{"id": k, "scenario": v, "description": DESCRIPTIONS.get(v, "")} for k, v in PRESETS.items()],
            "scenarios": [{"id": s, "description": DESCRIPTIONS.get(s, "")} for s in BENCHMARK_SCENARIOS + DEADLOCK_SCENARIOS],
            "custom": list_custom(),
            "edge_profiles": list(EDGE_PROFILES.keys()),
        }

    def benchmark(self) -> dict[str, Any]:
        out = {}
        for name in ("benchmark", "ablation"):
            p = RESULTS / f"{name}_summary.json"
            if p.exists():
                out[name] = json.loads(p.read_text(encoding="utf-8"))
        p = ROOT / "models" / "training_report.json"
        if p.exists():
            rep = json.loads(p.read_text(encoding="utf-8"))
            out["edge_ai"] = {k: rep.get(k) for k in ("conflict_model", "conflict_test", "conflict_test_rule_reference",
                                                       "deadlock_model", "deadlock_test", "ttc_test",
                                                       "inference_latency_portable_numpy", "model_file_bytes")}
        return out

    # ------------------------------------------------------------------ commands
    def command(self, msg: dict[str, Any]) -> dict[str, Any]:
        action = msg.get("action")
        with self.lock:
            sim = self.sim
            if action == "start":
                self.running = True
            elif action == "pause":
                self.running = False
            elif action == "step":
                if sim is not None:
                    sim.step()
                    if self.demo is not None and self.demo.active:
                        self.demo.on_tick(self)
            elif action == "reset":
                self.demo = None
                self.reset()
            elif action == "speed":
                v = float(msg.get("value", 1.0))
                self.tick_interval = max(0.03, min(2.0, 0.35 / max(0.1, v)))
            elif action == "configure":
                if "mode" in msg and msg["mode"] in MODES:
                    self.mode = msg["mode"]
                if "robots" in msg:
                    self.robots = max(1, min(20, int(msg["robots"])))
                if "seed" in msg:
                    self.seed = int(msg["seed"])
                if "scenario" in msg:
                    sc = msg["scenario"]
                    self.scenario = PRESETS.get(sc, sc)
                    self.custom = None
                if "edge_profile" in msg and msg["edge_profile"] in EDGE_PROFILES:
                    self.edge_profile = msg["edge_profile"]
                self.demo = None
                self.reset()
            elif action == "build_scenario":
                spec = msg.get("spec") or {}
                self.custom = spec
                self.seed = int(spec.get("seed", self.seed))
                if spec.get("mode") in MODES:
                    self.mode = spec["mode"]
                if msg.get("save_as"):
                    save_custom(spec, msg["save_as"])
                self.demo = None
                self.reset()
            elif action == "load_custom":
                self.custom = load_custom(msg["name"])
                self.seed = int(self.custom.get("seed", self.seed))
                self.demo = None
                self.reset()
            elif action == "event" and sim is not None:
                sim.apply_event(msg.get("event") or {})
                self._last_snapshot = None
            elif action == "demo":
                from src.command_center.demo import DemoDirector
                self.demo = DemoDirector()
                self.demo.start(self)
                self.running = True
            elif action == "stop_demo":
                self.demo = None
            else:
                return {"ok": False, "error": f"unknown action {action}"}
            self._last_snapshot = None
        return {"ok": True, "action": action}


_CONTROLLER: SwarmController | None = None


def get_controller() -> SwarmController:
    global _CONTROLLER
    if _CONTROLLER is None:
        _CONTROLLER = SwarmController()
    return _CONTROLLER
