# Changelog

## 1.1.0 (29 Sep 2026)
- **Baselines:** central PIBT (Okumura et al. 2019) with perfect information (`src/baselines/pibt.py`, §8f).
- **Scaling:** procedural 102×23 warehouse and a 25/50/100-AMR scaling experiment (`experiments/scaling_large.py`).
- **Experiments:** nonstop order stream (§8d), 12 s handling sensitivity (§8e), central-server outage (§8c).
- **Security:** the distributed runtime's UDP wire format is now JSON instead of pickle.
- **Deployment layout:** `deploy/{docker,edge,ros2}`, `configs/`, `datasets/`, `pyproject.toml`, `Makefile`, CI workflow.

## 1.0.0 (26 Sep 2026)
- EdgeSwarm decentralized engine, safety gate with proof, Edge-AI predictor, 3D Command Center, 30-seed benchmark,
  distributed one-process-per-robot runtime, message-loss stress test.
