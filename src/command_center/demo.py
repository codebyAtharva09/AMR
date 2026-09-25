"""Scripted SIH demo (Phase 21): seven scenes on a live EdgeSwarm simulation.

The director only *stages* situations (loads a scenario, blocks an aisle,
cancels a task, creates a Wi-Fi dead zone).  Everything the robots do in
response is their own decentralized behaviour, and every number shown in a
banner is read from the running simulation or from a freshly executed run.
If a situation does not occur in the time window (e.g. no high-risk conflict is
predicted), the banner says so instead of faking it.
"""
from __future__ import annotations

from typing import Any

from src.swarm.config import FULL, STOP_AND_WAIT, SwarmConfig
from src.swarm.engine import SwarmSimulation

DEMO_SCENARIO = "medium_congestion"
DEMO_SEED = 7
DEMO_ROBOTS = 5

SCENES = [
    (1, "Normal operations", "5 AMRs pick up and deliver with no central controller. Every robot plans on its own edge computer."),
    (2, "Predicted conflict", "Robots share their plans peer-to-peer. The Edge-AI model estimates each pair's conflict risk before anything happens."),
    (3, "Aisle blocked", "The central cross-aisle is blocked. Robots detect it, share it with peers, and compare waiting with detouring."),
    (4, "Task unavailable", "The warehouse system cancels a task a robot is already heading to. The robot releases it and the fleet re-allocates."),
    (5, "Wi-Fi dead zone", "A robot drives into a radio dead zone. It keeps working on its predictions and on-board sensing: DEGRADED, then PREDICTIVE_LOCAL."),
    (6, "Recovery", "Radio contact returns. The robot re-synchronises its state and reservations, then returns to CONNECTED."),
    (7, "Stop-and-wait vs EdgeSwarm", "The same scenario and seed, run with both strategies. The measured numbers are shown below."),
]


class DemoDirector:
    def __init__(self) -> None:
        self.active = False
        self.scene = 0
        self.scene_start = 0
        self.banner = ""
        self.details: dict[str, Any] = {}
        self.log: list[dict[str, Any]] = []
        self._dz_robot: str | None = None
        self._dz_end: int | None = None

    def status(self) -> dict[str, Any]:
        title = next((s[1] for s in SCENES if s[0] == self.scene), "")
        text = next((s[2] for s in SCENES if s[0] == self.scene), "")
        return {"active": self.active, "scene": self.scene, "total": len(SCENES), "title": title, "narration": text,
                "banner": self.banner, "details": self.details, "log": self.log[-12:]}

    def start(self, ctl) -> None:
        ctl.mode = FULL
        ctl.scenario = DEMO_SCENARIO
        ctl.robots = DEMO_ROBOTS
        ctl.seed = DEMO_SEED
        ctl.custom = None
        ctl.reset()
        self.active = True
        self._enter(ctl, 1)

    def _enter(self, ctl, scene: int) -> None:
        self.scene = scene
        self.scene_start = ctl.sim.tick
        self.details = {}
        self.banner = SCENES[scene - 1][2]
        self.log.append({"tick": ctl.sim.tick, "scene": scene, "title": SCENES[scene - 1][1]})
        sim = ctl.sim
        if scene == 3:
            sim.apply_event({"type": "block", "cells": [[8, 8], [9, 8]], "duration": 60, "label": "demo: cross-aisle blocked"})
        elif scene == 4:
            target = None
            for ag in sim.agents.values():
                if ag.state == "TO_PICKUP" and ag.task_id:
                    ts = sim.world.tasks.get(ag.task_id)
                    if ts and ts.picked_by is None:
                        target = ag
                        break
            if target:
                self.details = {"robot": target.robot_id, "task": target.task_id}
                sim.apply_event({"type": "cancel_task", "task": target.task_id})
            else:
                self.details = {"note": "no robot was approaching a pickup at this moment"}
        elif scene == 5:
            ag = next((a for a in sim.agents.values() if a.goal is not None), next(iter(sim.agents.values())))
            x, y = ag.pos
            self._dz_robot = ag.robot_id
            sim.apply_event({"type": "dead_zone", "rect": [x - 2, y - 2, x + 2, y + 2], "duration": 20})
            self._dz_end = sim.tick + 20
            self.details = {"robot": ag.robot_id, "dead_zone": [x - 2, y - 2, x + 2, y + 2]}
        elif scene == 7:
            self.details = self._comparison()
            self.banner = (f"Stop-and-wait makespan {self.details['stop_and_wait']['makespan']} ticks vs "
                           f"EdgeSwarm {self.details['edgeswarm']['makespan']} ticks "
                           f"({self.details['reduction_pct']:+.1f}%), collisions {self.details['stop_and_wait']['inter_robot_collisions']} / "
                           f"{self.details['edgeswarm']['inter_robot_collisions']} (single run, seed {DEMO_SEED}; "
                           "see the benchmark panel for 30-seed statistics)")

    def _recent(self, sim, kinds: tuple, since: int) -> list[dict]:
        out = []
        for ag in sim.agents.values():
            for d in ag.decisions:
                if d["kind"] in kinds and d["tick"] >= since:
                    out.append(d)
        return sorted(out, key=lambda d: d["tick"])

    def on_tick(self, ctl) -> None:
        if not self.active:
            return
        sim = ctl.sim
        el = sim.tick - self.scene_start
        if self.scene == 1 and el >= 25:
            self._enter(ctl, 2)
        elif self.scene == 2:
            ai = self._recent(sim, ("AI_PROACTIVE_REROUTE", "AI_CONTROLLED_WAIT"), self.scene_start)
            risks = [(ag.robot_id, r) for ag in sim.agents.values() for r in ag.last_risks]
            if risks:
                rid, top = max(risks, key=lambda x: x[1]["conflict"])
                self.details["highest_risk_now"] = {"robot": rid, **top}
            if ai:
                d = ai[0]
                ex = d.get("explanation", {})
                self.details["decision"] = d
                self.banner = (f"{d['robot']}: predicted conflict with {ex.get('peer')} p={ex.get('conflict_probability')} "
                               f"({ex.get('risk_level')}), action = {ex.get('action')}")
                if el >= 8:
                    self._enter(ctl, 3)
            elif el >= 60:
                self.banner = "No high-risk conflict was predicted in this 60-tick window. This is reported honestly, not staged."
                self._enter(ctl, 3)
        elif self.scene == 3:
            ev = self._recent(sim, ("BLOCKAGE_DETECTED", "PREDICTIVE_REROUTE"), self.scene_start)
            self.details["reroute_decisions"] = [d for d in ev if d["kind"] == "PREDICTIVE_REROUTE"][-4:]
            self.details["robots_that_detected"] = sorted({d["robot"] for d in ev if d["kind"] == "BLOCKAGE_DETECTED"})
            if el >= 30:
                self._enter(ctl, 4)
        elif self.scene == 4:
            ev = self._recent(sim, ("TASK_RELEASED", "TASK_CLAIMED"), self.scene_start)
            self.details["reassignment"] = ev[-4:]
            if el >= 15:
                self._enter(ctl, 5)
        elif self.scene == 5:
            ag = sim.agents.get(self._dz_robot) if self._dz_robot else None
            if ag:
                self.details["comm_mode"] = ag.comm_mode
                self.details["fleet_comm"] = {a.robot_id: a.comm_mode for a in sim.agents.values()}
            if self._dz_end is not None and sim.tick > self._dz_end:
                self._enter(ctl, 6)
        elif self.scene == 6:
            ev = self._recent(sim, ("COMM_RECOVERED",), self.scene_start - 2)
            self.details["recovered"] = ev[-5:]
            rec = [x for a in sim.agents.values() for x in a.recovery_times]
            self.details["recovery_times_ticks"] = rec[-5:]
            self.details["fleet_comm"] = {a.robot_id: a.comm_mode for a in sim.agents.values()}
            if el >= 12:
                self._enter(ctl, 7)
        elif self.scene == 7:
            if el >= 25:
                self.active = False

    def _comparison(self) -> dict[str, Any]:
        res = {}
        for mode, key in ((STOP_AND_WAIT, "stop_and_wait"), (FULL, "edgeswarm")):
            cfg = SwarmConfig(mode=mode, seed=DEMO_SEED, robots=DEMO_ROBOTS, tasks=4 * DEMO_ROBOTS, scenario=DEMO_SCENARIO)
            m = SwarmSimulation(cfg).run()
            res[key] = {k: m[k] for k in ("makespan", "avg_task_completion_time", "inter_robot_collisions", "near_collisions",
                                          "wait_time", "total_distance", "replanning_count", "messages_sent", "all_completed")}
        b, p = res["stop_and_wait"]["makespan"], res["edgeswarm"]["makespan"]
        res["reduction_pct"] = round(100.0 * (b - p) / b, 2)
        res["note"] = f"single run, scenario {DEMO_SCENARIO}, seed {DEMO_SEED}, {DEMO_ROBOTS} AMRs"
        return res


def run_headless_demo() -> dict[str, Any]:
    """CLI version: runs the same seven scenes without a browser and prints the narration."""
    class _Ctl:
        pass
    from src.command_center.controller import SwarmController  # noqa: F401  (import check)
    ctl = _Ctl()
    ctl.mode, ctl.scenario, ctl.robots, ctl.seed, ctl.custom = FULL, DEMO_SCENARIO, DEMO_ROBOTS, DEMO_SEED, None
    cfg = SwarmConfig(mode=FULL, seed=DEMO_SEED, robots=DEMO_ROBOTS, tasks=4 * DEMO_ROBOTS, scenario=DEMO_SCENARIO)
    ctl.sim = SwarmSimulation(cfg)
    ctl.reset = lambda: None
    d = DemoDirector()
    d.active = True
    d._enter(ctl, 1)
    last_scene = 0
    printed = []
    while d.active and ctl.sim.tick < 600:
        ctl.sim.step()
        d.on_tick(ctl)
        if d.scene != last_scene:
            st = d.status()
            line = f"[t={ctl.sim.tick:4d}] SCENE {st['scene']}/7 {st['title']}: {st['narration']}"
            print(line)
            printed.append(line)
            last_scene = d.scene
    print("\nFINAL:", d.banner)
    return {"log": d.log, "comparison": d.details, "lines": printed}
