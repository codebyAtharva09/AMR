# Deployment

| Folder | What runs there | Status |
|---|---|---|
| `docker/Dockerfile.server` + `docker-compose.yml` | Operator PC: 3D Command Center (watch-only) and the CLI | builds; dashboard verified locally |
| `docker/Dockerfile.edge` | Robot computer: agent + Edge-AI (NumPy only), multi-arch | builds; **not yet run on a Pi/Jetson** |
| `edge/edge_benchmark.py` | Times the per-robot decision loop on the target board | ready to run on hardware |
| `edge/edgeswarm-robot.service` | systemd unit for the robot computer | template |
| `ros2/` | `RobotState.msg` + topic/QoS mapping for the ROS 2 node | interface spec; node is finale work |

Nothing here claims hardware results until `edge/edge_benchmark.py` has produced a file on a real board.
