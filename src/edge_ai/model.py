"""Portable, numpy-only inference for the Edge-AI conflict predictor.

Training uses scikit-learn (offline, on a workstation).  The trained models are
exported to a single JSON file holding plain arrays, so that the on-robot runtime
needs only numpy (no scikit-learn, no deep-learning framework).  Supported model
families: logistic regression, small MLP (ReLU), and tree ensembles (random
forest / gradient boosting), each with an optional standard scaler.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import numpy as np


class PortableModel:
    """One exported estimator: predict_proba for classifiers, predict for regressors."""

    def __init__(self, spec: dict[str, Any]):
        self.spec = spec
        self.kind = spec["kind"]
        sc = spec.get("scaler")
        self.mean = np.asarray(sc["mean"], dtype=np.float64) if sc else None
        self.scale = np.asarray(sc["scale"], dtype=np.float64) if sc else None
        if self.kind == "logreg":
            self.coef = np.asarray(spec["coef"], dtype=np.float64)
            self.intercept = float(spec["intercept"])
        elif self.kind == "mlp":
            self.W = [np.asarray(w, dtype=np.float64) for w in spec["weights"]]
            self.b = [np.asarray(b, dtype=np.float64) for b in spec["biases"]]
            self.out_act = spec.get("out_activation", "logistic")
        elif self.kind in ("forest", "gbm"):
            self.trees = []
            for t in spec["trees"]:
                self.trees.append({
                    "feature": np.asarray(t["feature"], dtype=np.int64),
                    "threshold": np.asarray(t["threshold"], dtype=np.float64),
                    "left": np.asarray(t["left"], dtype=np.int64),
                    "right": np.asarray(t["right"], dtype=np.int64),
                    "value": np.asarray(t["value"], dtype=np.float64),
                    "depth": int(t["depth"]),
                })
            # pad all trees into (n_trees, max_nodes) arrays so the whole ensemble is evaluated
            # in one vectorised pass per depth level
            T = len(self.trees)
            M = max(len(t["feature"]) for t in self.trees)
            self._F = np.full((T, M), -1, dtype=np.int64)
            self._TH = np.zeros((T, M))
            self._L = np.zeros((T, M), dtype=np.int64)
            self._R = np.zeros((T, M), dtype=np.int64)
            self._V = np.zeros((T, M))
            for i, t in enumerate(self.trees):
                n = len(t["feature"])
                self._F[i, :n] = t["feature"]
                self._TH[i, :n] = t["threshold"]
                self._L[i, :n] = t["left"]
                self._R[i, :n] = t["right"]
                self._V[i, :n] = t["value"]
            self._D = max(t["depth"] for t in self.trees)
            self.init = float(spec.get("init", 0.0))
            self.learning_rate = float(spec.get("learning_rate", 1.0))
        else:
            raise ValueError(f"unknown model kind {self.kind}")
        self.task = spec.get("task", "classification")

    def _prep(self, X: np.ndarray) -> np.ndarray:
        X = np.asarray(X, dtype=np.float64)
        if self.mean is not None:
            X = (X - self.mean) / self.scale
        return X

    @staticmethod
    def _tree_eval(t: dict[str, np.ndarray], X: np.ndarray) -> np.ndarray:
        node = np.zeros(X.shape[0], dtype=np.int64)
        rows = np.arange(X.shape[0])
        for _ in range(t["depth"] + 1):
            feat = t["feature"][node]
            leaf = feat < 0
            if leaf.all():
                break
            f = np.where(leaf, 0, feat)
            go_left = X[rows, f] <= t["threshold"][node]
            nxt = np.where(go_left, t["left"][node], t["right"][node])
            node = np.where(leaf, node, nxt)
        return t["value"][node]

    def _ensemble_eval(self, X: np.ndarray) -> np.ndarray:
        """Sum of leaf values over all trees, vectorised over (trees x samples)."""
        T = self._F.shape[0]
        S = X.shape[0]
        ti = np.arange(T)[:, None]
        si = np.arange(S)[None, :]
        node = np.zeros((T, S), dtype=np.int64)
        for _ in range(self._D + 1):
            f = self._F[ti, node]
            leaf = f < 0
            if leaf.all():
                break
            xv = X[si, np.where(leaf, 0, f)]
            nxt = np.where(xv <= self._TH[ti, node], self._L[ti, node], self._R[ti, node])
            node = np.where(leaf, node, nxt)
        return self._V[ti, node].sum(axis=0)

    def raw(self, X: np.ndarray) -> np.ndarray:
        X = np.asarray(X, dtype=np.float64)
        if X.shape[0] > 20000:  # bound memory of the vectorised ensemble evaluation
            return np.concatenate([self.raw(X[i:i + 20000]) for i in range(0, X.shape[0], 20000)])
        X = self._prep(X)
        if self.kind == "logreg":
            z = X @ self.coef + self.intercept
            return 1.0 / (1.0 + np.exp(-np.clip(z, -50, 50))) if self.task == "classification" else z
        if self.kind == "mlp":
            h = X
            for i, (W, b) in enumerate(zip(self.W, self.b)):
                h = h @ W + b
                if i < len(self.W) - 1:
                    h = np.maximum(h, 0.0)
            h = h.reshape(-1)
            if self.task == "classification":
                return 1.0 / (1.0 + np.exp(-np.clip(h, -50, 50)))
            return h
        if self.kind == "forest":
            return self._ensemble_eval(X) / len(self.trees)
        # gbm
        acc = self.init + self.learning_rate * self._ensemble_eval(X)
        if self.task == "classification":
            return 1.0 / (1.0 + np.exp(-np.clip(acc, -50, 50)))
        return acc


class ConflictPredictor:
    """Bundle of three heads: conflict probability, deadlock probability, time-to-conflict."""

    def __init__(self, bundle: dict[str, Any]):
        self.bundle = bundle
        self.feature_names = bundle["feature_names"]
        self.conflict = PortableModel(bundle["conflict"])
        self.deadlock = PortableModel(bundle["deadlock"]) if bundle.get("deadlock") else None
        self.ttc = PortableModel(bundle["ttc"]) if bundle.get("ttc") else None
        self.meta = bundle.get("meta", {})
        self.expected_delay_given_conflict = float(self.meta.get("expected_delay_given_conflict", 3.0))
        self.expected_delay_given_deadlock = float(self.meta.get("expected_delay_given_deadlock", 8.0))
        self.conflict_threshold = float(self.meta.get("conflict_threshold", 0.5))
        self.deadlock_threshold = float(self.meta.get("deadlock_threshold", 0.5))
        self.action_conflict_threshold = float(self.meta.get("action_conflict_threshold", max(0.5, self.conflict_threshold)))
        self.action_deadlock_threshold = float(self.meta.get("action_deadlock_threshold", max(0.5, self.deadlock_threshold)))
        self.calls = 0
        self.rows = 0
        self.total_s = 0.0

    @classmethod
    def load(cls, path: str | Path) -> "ConflictPredictor":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def size_bytes(self) -> int:
        return len(json.dumps(self.bundle, separators=(",", ":")))

    def predict(self, X) -> dict[str, np.ndarray]:
        X = np.asarray(X, dtype=np.float64)
        if X.ndim == 1:
            X = X.reshape(1, -1)
        t0 = time.perf_counter()
        pc = self.conflict.raw(X)
        pdl = self.deadlock.raw(X) if self.deadlock else np.zeros(len(X))
        ttc = self.ttc.raw(X) if self.ttc else np.full(len(X), -1.0)
        self.total_s += time.perf_counter() - t0
        self.calls += 1
        self.rows += len(X)
        return {"conflict": np.clip(pc, 0, 1), "deadlock": np.clip(pdl, 0, 1), "ttc": np.clip(ttc, 0, None)}

    def latency_stats(self) -> dict[str, float]:
        return {
            "calls": self.calls,
            "rows": self.rows,
            "mean_ms_per_call": round(1000 * self.total_s / self.calls, 4) if self.calls else 0.0,
            "mean_us_per_pair": round(1e6 * self.total_s / self.rows, 2) if self.rows else 0.0,
        }


def risk_level(p: float) -> str:
    """Human-readable confidence band used in explanations / dashboard."""
    if p >= 0.75:
        return "HIGH"
    if p >= 0.5:
        return "ELEVATED"
    if p >= 0.25:
        return "MODERATE"
    return "LOW"
