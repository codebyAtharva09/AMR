"""Train, evaluate, select and export the Edge-AI conflict predictor (Phases 4 and 16).

    python3 -m src.edge_ai.train            (or: python3 main.py --mode train-ai)

Pipeline
  1. Generate labelled pair data from rule-based rollouts (dataset.py).
     Train seeds, validation seeds and test seeds are disjoint whole episodes.
     Training negatives are sub-sampled (x0.35) and re-weighted; validation and
     test sets keep the true class balance.
  2. Candidates: logistic regression (baseline), random forest, small MLP,
     gradient boosting, plus a hand-written rule as a non-ML reference.
  3. Selection on validation F1 (decision threshold tuned on validation only).
  4. Test-set report: accuracy, precision, recall, F1, confusion matrix, ROC-AUC,
     PR-AUC, and a scenario hold-out (out-of-distribution) check.
  5. Export the chosen models to models/conflict_model.json (numpy-only runtime)
     and measure inference latency with the portable runtime.
"""
from __future__ import annotations

import json
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np

from src.edge_ai.dataset import H_CONFLICT, H_DEADLOCK, generate_episode
from src.edge_ai.features import FEATURE_NAMES
from src.edge_ai.model import ConflictPredictor
from src.swarm.scenarios import BENCHMARK_SCENARIOS

ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = ROOT / "models" / "conflict_model.json"
REPORT_PATH = ROOT / "models" / "training_report.json"

TRAIN_SEEDS = list(range(1001, 1013))
VAL_SEEDS = list(range(2001, 2005))
TEST_SEEDS = list(range(3001, 3009))
SIZES = [5, 10, 15]
TRAIN_NEG_KEEP = 0.35


def _episode(args):
    sc, n, s, neg = args
    ep = generate_episode(sc, n, s, neg_keep=neg)
    ep["scenario"] = sc
    return ep


def build_split(seeds, neg_keep, scenarios, workers=2):
    jobs = [(sc, n, s, neg_keep) for sc in scenarios for n in SIZES for s in seeds]
    with Pool(workers) as pool:
        eps = pool.map(_episode, jobs, chunksize=2)
    return {
        "X": np.concatenate([e["X"] for e in eps]).astype(np.float64),
        "yc": np.concatenate([e["y_conflict"] for e in eps]).astype(int),
        "yd": np.concatenate([e["y_deadlock"] for e in eps]).astype(int),
        "ttc": np.concatenate([e["ttc"] for e in eps]).astype(np.float64),
        "sc": np.concatenate([np.array([e["scenario"]] * len(e["X"])) for e in eps]),
        "blocked_mean": float(np.mean([e["blocked_mean"] for e in eps])),
        "episodes": len(eps),
    }


# ---------------------------------------------------------------------------- export helpers
def _scaler(sc):
    return {"mean": sc.mean_.tolist(), "scale": sc.scale_.tolist()}


def export_logreg(clf, sc):
    return {"kind": "logreg", "task": "classification", "scaler": _scaler(sc),
            "coef": clf.coef_[0].tolist(), "intercept": float(clf.intercept_[0])}


def export_mlp(clf, sc, task="classification"):
    return {"kind": "mlp", "task": task, "scaler": _scaler(sc),
            "weights": [w.tolist() for w in clf.coefs_], "biases": [b.tolist() for b in clf.intercepts_]}


def _tree(t, value):
    return {"feature": [int(f) if f >= 0 else -1 for f in t.feature], "threshold": t.threshold.tolist(),
            "left": t.children_left.tolist(), "right": t.children_right.tolist(),
            "value": [float(v) for v in value], "depth": int(t.max_depth)}


def export_forest(rf, task="classification"):
    trees = []
    for est in rf.estimators_:
        t = est.tree_
        if task == "classification":
            v = t.value[:, 0, :]
            v = v[:, 1] / np.maximum(v.sum(axis=1), 1e-12)
        else:
            v = t.value[:, 0, 0]
        trees.append(_tree(t, v))
    return {"kind": "forest", "task": task, "scaler": None, "trees": trees}


def export_gbm(gb, task="classification"):
    trees = [_tree(e[0].tree_, e[0].tree_.value[:, 0, 0]) for e in gb.estimators_]
    if task == "classification":
        p = float(gb.init_.class_prior_[1]) if hasattr(gb.init_, "class_prior_") else 0.5
        init = float(np.log(p / (1 - p)))
    else:
        init = float(gb.init_.constant_[0][0]) if hasattr(gb.init_, "constant_") else 0.0
    return {"kind": "gbm", "task": task, "scaler": None, "trees": trees, "init": init,
            "learning_rate": float(gb.learning_rate)}


# ---------------------------------------------------------------------------- metrics
def cls_metrics(y, p, thr):
    from sklearn.metrics import average_precision_score, roc_auc_score
    yhat = (p >= thr).astype(int)
    tp = int(((yhat == 1) & (y == 1)).sum())
    tn = int(((yhat == 0) & (y == 0)).sum())
    fp = int(((yhat == 1) & (y == 0)).sum())
    fn = int(((yhat == 0) & (y == 1)).sum())
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    out = {"threshold": round(float(thr), 3), "n": int(len(y)), "positives": int(y.sum()),
           "accuracy": round((tp + tn) / max(1, len(y)), 4), "precision": round(prec, 4), "recall": round(rec, 4),
           "f1": round(f1, 4), "confusion_matrix": {"tn": tn, "fp": fp, "fn": fn, "tp": tp}}
    if 0 < y.sum() < len(y):
        out["roc_auc"] = round(float(roc_auc_score(y, p)), 4)
        out["pr_auc"] = round(float(average_precision_score(y, p)), 4)
    return out


def best_threshold(y, p):
    best = (0.0, 0.5)
    for thr in np.linspace(0.05, 0.95, 91):
        m = cls_metrics(y, p, thr)
        if m["f1"] > best[0]:
            best = (m["f1"], thr)
    return best[1]


def rule_score(X):
    """Non-ML reference: overlapping plans with small temporal gap, closer than 4 cells."""
    i = {n: k for k, n in enumerate(FEATURE_NAMES)}
    s = (X[:, i["path_overlap"]] > 0) & (X[:, i["temporal_gap"]] <= 2) & (X[:, i["rel_dist"]] <= 4)
    return s.astype(float)


def _cap(split, n, seed):
    """Uniform row sub-sample of a split (keeps the split's seed membership)."""
    if len(split["X"]) <= n:
        return split
    idx = np.random.default_rng(seed).choice(len(split["X"]), n, replace=False)
    out = dict(split)
    for k in ("X", "yc", "yd", "ttc", "sc"):
        out[k] = split[k][idx]
    return out


def _fit_candidates(Xtr, ytr, wtr, Xva, yva, seed=0, only=None):
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.neural_network import MLPClassifier
    from sklearn.preprocessing import StandardScaler
    sc = StandardScaler().fit(Xtr)
    Xs, Xvs = sc.transform(Xtr), sc.transform(Xva)
    cands = {}
    want = (lambda k: only is None or k in only)
    t0 = time.time()
    lr = LogisticRegression(max_iter=2000, C=1.0).fit(Xs, ytr, sample_weight=wtr)
    cands["logistic_regression"] = (lr.predict_proba(Xvs)[:, 1], export_logreg(lr, sc), time.time() - t0)
    t0 = time.time()
    if want("random_forest"):
        rf = RandomForestClassifier(n_estimators=40, max_depth=9, min_samples_leaf=20, n_jobs=2, random_state=seed)
        rf.fit(Xtr, ytr, sample_weight=wtr)
        cands["random_forest"] = (rf.predict_proba(Xva)[:, 1], export_forest(rf), time.time() - t0)
    if not want("mlp_32x16") and not want("gradient_boosting"):
        return cands
    t0 = time.time()
    # MLP has no sample_weight in sklearn: rebalance by replicating negatives' weight via resampling
    rng = np.random.default_rng(seed)
    reps = np.where(wtr > 1.0, np.round(wtr).astype(int), 1)
    idx = np.repeat(np.arange(len(Xs)), reps)
    rng.shuffle(idx)
    if want("mlp_32x16"):
        mlp = MLPClassifier(hidden_layer_sizes=(32, 16), max_iter=40, early_stopping=True, random_state=seed)
        mlp.fit(Xs[idx], ytr[idx])
        cands["mlp_32x16"] = (mlp.predict_proba(Xvs)[:, 1], export_mlp(mlp, sc), time.time() - t0)
    t0 = time.time()
    if not want("gradient_boosting"):
        return cands
    gb = GradientBoostingClassifier(n_estimators=120, max_depth=3, learning_rate=0.1, subsample=0.8, random_state=seed)
    gb.fit(Xtr, ytr, sample_weight=wtr)
    cands["gradient_boosting"] = (gb.predict_proba(Xva)[:, 1], export_gbm(gb), time.time() - t0)
    return cands


def main(workers: int = 2) -> dict:
    t_start = time.time()
    scen = BENCHMARK_SCENARIOS
    print("[edge-ai] generating data ...", flush=True)
    cache = ROOT / "data" / "edge_ai_splits.npz"
    if cache.exists():
        z = np.load(cache, allow_pickle=True)
        tr, va, te = z["tr"].item(), z["va"].item(), z["te"].item()
        print(f"[edge-ai] loaded cached splits from {cache}", flush=True)
    else:
        tr = build_split(TRAIN_SEEDS, TRAIN_NEG_KEEP, scen, workers)
        va = build_split(VAL_SEEDS, 1.0, scen, workers)
        te = build_split(TEST_SEEDS, 1.0, scen, workers)
        cache.parent.mkdir(parents=True, exist_ok=True)
        np.savez(cache, tr=np.array(tr, dtype=object), va=np.array(va, dtype=object), te=np.array(te, dtype=object))
    print(f"[edge-ai] rows train={len(tr['X'])} val={len(va['X'])} test={len(te['X'])}", flush=True)
    full_rows = {"train": int(len(tr["X"])), "val": int(len(va["X"]))}
    tr = _cap(tr, 250_000, 1)
    va = _cap(va, 150_000, 2)
    print(f"[edge-ai] capped train={len(tr['X'])} val={len(va['X'])}; fitting candidates ...", flush=True)
    wtr = np.where(tr["yc"] == 1, 1.0, 1.0 / TRAIN_NEG_KEEP)

    report = {"feature_names": FEATURE_NAMES, "horizons": {"conflict": H_CONFLICT, "deadlock": H_DEADLOCK},
              "splits": {"train_seeds": TRAIN_SEEDS, "val_seeds": VAL_SEEDS, "test_seeds": TEST_SEEDS,
                         "fleet_sizes": SIZES, "scenarios": scen, "train_negative_keep": TRAIN_NEG_KEEP,
                         "rows": {"train": int(len(tr["X"])), "val": int(len(va["X"])), "test": int(len(te["X"])),
                                  "generated_before_cap": full_rows, "cap_note": "uniform row sample of train/val splits for training time; test uses every row"},
                         "positive_rate": {"train_conflict_raw": round(float(tr["yc"].mean()), 4),
                                           "val_conflict": round(float(va["yc"].mean()), 4),
                                           "test_conflict": round(float(te["yc"].mean()), 4),
                                           "val_deadlock": round(float(va["yd"].mean()), 5),
                                           "test_deadlock": round(float(te["yd"].mean()), 5)}},
              "behaviour_policy": "reservation (rule-based, no AI in the loop)"}

    # ---------------- conflict head
    cands = _fit_candidates(tr["X"], tr["yc"], wtr, va["X"], va["yc"])
    print("[edge-ai] conflict candidates fitted", flush=True)
    val_table = {}
    for name, (pva, spec, secs) in cands.items():
        thr = best_threshold(va["yc"], pva)
        val_table[name] = {**cls_metrics(va["yc"], pva, thr), "train_seconds": round(secs, 1),
                           "export_bytes": len(json.dumps(spec, separators=(",", ":")))}
    rule_va = rule_score(va["X"])
    val_table["rule_based_reference"] = cls_metrics(va["yc"], rule_va, 0.5)
    chosen = max(cands, key=lambda k: (val_table[k]["f1"], -val_table[k]["export_bytes"]))
    thr_c = val_table[chosen]["threshold"]
    conflict_spec = cands[chosen][1]
    report["conflict_validation"] = val_table
    report["conflict_model"] = chosen

    # ---------------- deadlock head (same family as chosen; falls back to logistic if too few positives)
    dl_spec = None
    thr_d = 0.5
    if tr["yd"].sum() >= 30 and va["yd"].sum() >= 5:
        wd = np.where(tr["yd"] == 1, 1.0, np.where(tr["yc"] == 1, 1.0, 1.0 / TRAIN_NEG_KEEP))
        dc = _fit_candidates(tr["X"], tr["yd"], wd, va["X"], va["yd"], only={"random_forest", "gradient_boosting"})
        dval = {}
        for name, (pva, spec, secs) in dc.items():
            thr = best_threshold(va["yd"], pva)
            dval[name] = {**cls_metrics(va["yd"], pva, thr), "export_bytes": len(json.dumps(spec, separators=(",", ":")))}
        dchosen = max(dc, key=lambda k: (dval[k]["f1"], -dval[k]["export_bytes"]))
        dl_spec = dc[dchosen][1]
        thr_d = dval[dchosen]["threshold"]
        report["deadlock_validation"] = dval
        report["deadlock_model"] = dchosen
    else:
        report["deadlock_model"] = None
        report["deadlock_note"] = "too few deadlock positives to train"

    # ---------------- time-to-conflict regression (positives only)
    from sklearn.ensemble import RandomForestRegressor
    pos = tr["yc"] == 1
    rfr = RandomForestRegressor(n_estimators=20, max_depth=7, min_samples_leaf=20, n_jobs=2, random_state=0)
    rfr.fit(tr["X"][pos], tr["ttc"][pos])
    ttc_spec = export_forest(rfr, task="regression")

    bundle = {"version": 1, "feature_names": FEATURE_NAMES, "conflict": conflict_spec, "deadlock": dl_spec,
              "ttc": ttc_spec, "meta": {
                  "conflict_threshold": thr_c, "deadlock_threshold": thr_d,
                  "expected_delay_given_conflict": round(max(1.0, tr["blocked_mean"]), 3),
                  "expected_delay_given_deadlock": 8.0,
                  "horizon_conflict": H_CONFLICT, "horizon_deadlock": H_DEADLOCK,
                  "conflict_model": chosen, "deadlock_model": report.get("deadlock_model"),
                  "trained_on": "EdgeSwarm reservation-mode rollouts (simulation only)"}}
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    MODEL_PATH.write_text(json.dumps(bundle, separators=(",", ":")), encoding="utf-8")

    # ---------------- test evaluation with the exported portable runtime
    pred = ConflictPredictor.load(MODEL_PATH)
    out = pred.predict(te["X"])
    report["conflict_test"] = cls_metrics(te["yc"], out["conflict"], thr_c)
    report["conflict_test_rule_reference"] = cls_metrics(te["yc"], rule_score(te["X"]), 0.5)
    per_sc = {}
    for sc in scen:
        m = te["sc"] == sc
        if m.sum():
            per_sc[sc] = cls_metrics(te["yc"][m], out["conflict"][m], thr_c)
    report["conflict_test_per_scenario"] = per_sc
    if dl_spec is not None:
        report["deadlock_test"] = cls_metrics(te["yd"], out["deadlock"], thr_d)
    posm = te["yc"] == 1
    if posm.sum():
        err = np.abs(out["ttc"][posm] - te["ttc"][posm])
        base = np.abs(np.mean(tr["ttc"][pos]) - te["ttc"][posm])
        report["ttc_test"] = {"mae_ticks": round(float(err.mean()), 3), "baseline_mae_predict_mean": round(float(base.mean()), 3),
                              "n": int(posm.sum())}

    # ---------------- out-of-distribution check: train without narrow_intersection, test on it
    ood_sc = "narrow_intersection"
    m_tr = tr["sc"] != ood_sc
    m_te = te["sc"] == ood_sc
    if m_te.sum():
        from sklearn.ensemble import GradientBoostingClassifier
        spec_family = chosen
        ood = _fit_candidates(tr["X"][m_tr], tr["yc"][m_tr], wtr[m_tr], va["X"][va["sc"] != ood_sc], va["yc"][va["sc"] != ood_sc],
                              only={spec_family})
        pva, spec, _ = ood[spec_family]
        thr = best_threshold(va["yc"][va["sc"] != ood_sc], pva)
        from src.edge_ai.model import PortableModel
        p = PortableModel(spec).raw(te["X"][m_te])
        report["ood_holdout"] = {"held_out_scenario": ood_sc, "model": spec_family,
                                 "test_on_held_out": cls_metrics(te["yc"][m_te], p, thr),
                                 "in_distribution_same_scenario": per_sc.get(ood_sc)}

    # ---------------- latency of the portable runtime
    lat = {}
    for batch in (1, 8, 32):
        Xb = te["X"][:batch]
        reps = 300 if batch < 32 else 100
        t0 = time.perf_counter()
        for _ in range(reps):
            pred.predict(Xb)
        dt = (time.perf_counter() - t0) / reps
        lat[f"batch_{batch}"] = {"ms_per_call": round(dt * 1000, 4), "us_per_pair": round(dt * 1e6 / batch, 2)}
    report["inference_latency_portable_numpy"] = lat
    report["model_file_bytes"] = MODEL_PATH.stat().st_size
    report["total_seconds"] = round(time.time() - t_start, 1)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("conflict_model", "conflict_test", "deadlock_model", "model_file_bytes")}, indent=2))
    return report


if __name__ == "__main__":
    main()
