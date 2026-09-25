"""Edge-AI tests: features, leakage, portable export equivalence, runtime, influence on decisions."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from src.edge_ai.features import FEATURE_NAMES, N_FEATURES, pair_features
from src.edge_ai.model import ConflictPredictor, PortableModel
from src.swarm.config import RESERVATION, RESERVATION_AI, SwarmConfig
from src.swarm.engine import SwarmSimulation

MODEL = Path(__file__).resolve().parents[1] / "models" / "conflict_model.json"
needs_model = pytest.mark.skipif(not MODEL.exists(), reason="trained model not present")


def _warm_sim(steps=15):
    sim = SwarmSimulation(SwarmConfig(mode=RESERVATION, seed=3, robots=8, tasks=32, scenario="high_congestion"))
    for _ in range(steps):
        sim.step()
    return sim


def test_feature_vector_shape_and_finiteness():
    sim = _warm_sim()
    n = 0
    for ag in sim.agents.values():
        for b in ag.beliefs.values():
            f = pair_features(ag, b, sim.tick)
            assert len(f) == N_FEATURES == len(FEATURE_NAMES)
            assert all(math.isfinite(x) for x in f)
            n += 1
    assert n > 0


def test_features_do_not_read_ground_truth_of_peers():
    """Leakage guard: moving a peer's TRUE body must not change features (only beliefs may)."""
    sim = _warm_sim()
    ag = next(iter(sim.agents.values()))
    b = next(iter(ag.beliefs.values()))
    before = pair_features(ag, b, sim.tick)
    body = sim.world.bodies[b.robot_id]
    body.pos = (1, 1)
    body.battery = 3.0
    body.carrying = "XYZ"
    after = pair_features(ag, b, sim.tick)
    assert before == after


def _toy_data(seed=0, n=600):
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n, 5))
    y = ((X[:, 0] + 0.5 * X[:, 1] - X[:, 2] * X[:, 3]) > 0).astype(int)
    return X, y


def test_portable_export_matches_sklearn():
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.neural_network import MLPClassifier
    from sklearn.preprocessing import StandardScaler

    from src.edge_ai.train import export_forest, export_gbm, export_logreg, export_mlp
    X, y = _toy_data()
    sc = StandardScaler().fit(X)
    lr = LogisticRegression().fit(sc.transform(X), y)
    np.testing.assert_allclose(PortableModel(export_logreg(lr, sc)).raw(X), lr.predict_proba(sc.transform(X))[:, 1], atol=1e-9)
    mlp = MLPClassifier(hidden_layer_sizes=(8,), max_iter=300, random_state=0).fit(sc.transform(X), y)
    np.testing.assert_allclose(PortableModel(export_mlp(mlp, sc)).raw(X), mlp.predict_proba(sc.transform(X))[:, 1], atol=1e-9)
    rf = RandomForestClassifier(n_estimators=7, max_depth=5, random_state=0).fit(X, y)
    np.testing.assert_allclose(PortableModel(export_forest(rf)).raw(X), rf.predict_proba(X)[:, 1], atol=1e-9)
    gb = GradientBoostingClassifier(n_estimators=15, max_depth=3, random_state=0).fit(X, y)
    np.testing.assert_allclose(PortableModel(export_gbm(gb)).raw(X), gb.predict_proba(X)[:, 1], atol=1e-9)


@needs_model
def test_trained_model_runtime_and_latency():
    import time
    p = ConflictPredictor.load(MODEL)
    assert p.feature_names == FEATURE_NAMES
    X = np.random.default_rng(1).normal(size=(32, N_FEATURES)) * 2 + 3
    out = p.predict(X)
    for k in ("conflict", "deadlock"):
        assert out[k].shape == (32,) and np.all((out[k] >= 0) & (out[k] <= 1))
    t0 = time.perf_counter()
    for _ in range(50):
        p.predict(X)
    assert (time.perf_counter() - t0) / 50 < 0.05  # < 50 ms for 32 pairs even on slow CI
    assert p.size_bytes() < 2_000_000


@needs_model
def test_ai_predictions_change_decisions():
    """The AI must actually drive behaviour: forcing it always-on vs always-off changes the run."""
    def run(tc, td):
        cfg = SwarmConfig(mode=RESERVATION_AI, seed=5, robots=10, tasks=40, scenario="high_congestion",
                          ai_conflict_threshold=tc, ai_deadlock_threshold=td)
        return SwarmSimulation(cfg).run()
    on = run(0.0, 0.0)
    off = run(1.01, 1.01)
    assert on["ai_evaluations"] > 0 and off["ai_evaluations"] > 0
    assert on["proactive_reroutes"] + on["proactive_waits"] > 0
    assert off["proactive_reroutes"] + off["proactive_waits"] == 0
    assert (on["makespan"], on["total_distance"]) != (off["makespan"], off["total_distance"])
    assert on["inter_robot_collisions"] == 0 and off["inter_robot_collisions"] == 0
    assert on["ai_inference"]["rows"] > 0 and on["ai_inference"]["mean_us_per_pair"] > 0
