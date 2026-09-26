# ROS 2 bridge: interface specification (next step, not yet implemented)

Status: **specification only**. The coordinator is already one process per robot, talking only through serialised
messages (`src/swarm/distributed.py`). It reproduces the in-process simulation exactly in 20 out of 20 runs
(`experiments/results/distributed_check.json`). Moving it to ROS 2 therefore means swapping the transport, not
changing the logic.

| EdgeSwarm today | ROS 2 target |
|---|---|
| One OS process per robot (`RobotAgent`) | One `rclpy` node per robot, running on its own Raspberry Pi 4 / Jetson |
| STATE message over UDP through the radio emulator | Topic `/fleet/state` (`edgeswarm_msgs/RobotState`), QoS `BEST_EFFORT`, depth 1, over Zenoh or DDS |
| Warehouse system task list (WMS broadcast) | Topic `/wms/tasks` (reliable, transient-local) |
| `env.try_pickup` / `env.complete_drop` | Services `/station/<id>/pickup`, `/station/<id>/drop` |
| World sensing (robots, humans and blockages within radius) | LiDAR → `nav2_costmap_2d` layers + robot detections |
| Safety layer "enter only if sensed empty and no fresh higher-priority declaration" | Unchanged: runs inside the node before each velocity command |
| Cell move per tick | Nav2 `FollowPath` on a lane graph; one cell = one waypoint |

Why BEST_EFFORT: the safety rule already assumes messages can be lost, and it only trusts fresh messages. Retransmitting
old state would only add latency.
