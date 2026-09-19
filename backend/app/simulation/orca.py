"""ORCA-inspired reciprocal velocity obstacle avoidance.

Each agent only sees the broadcast (position, velocity, radius) of neighbors within
its own communication range - there is no shared/global state here, so this function
is safe to run independently on every robot's own onboard compute.
"""
from __future__ import annotations

import numpy as np

AGENT_RADIUS = 0.5
SAFETY_MARGIN = 0.35
TIME_HORIZON = 3.0


class NeighborState:
    __slots__ = ("agent_id", "pos", "vel", "radius")

    def __init__(self, agent_id: str, pos: np.ndarray, vel: np.ndarray, radius: float):
        self.agent_id = agent_id
        self.pos = pos
        self.vel = vel
        self.radius = radius


def _orca_half_plane_adjust(
    rel_pos: np.ndarray, self_vel: np.ndarray, neighbor_vel: np.ndarray, combined_radius: float
) -> np.ndarray | None:
    """Returns a velocity correction vector (applied to the agent) that pushes the
    agent's velocity outside the collision cone, or None if no correction is needed.

    rel_pos points from self to neighbor (neighbor.pos - self.pos). The relative
    trajectory neighbor-minus-self position evolves as rel_pos + t*(neighbor_vel -
    self_vel), so that combination (not self_vel - neighbor_vel) is what must be used
    to find the future closest approach."""
    dist = np.linalg.norm(rel_pos)
    if dist < 1e-6:
        dist = 1e-6

    if dist < combined_radius:
        # Already inside the safety radius: push straight apart (emergency separation).
        direction = -rel_pos / dist
        return direction * (combined_radius - dist) * 2.0

    traj_vel = neighbor_vel - self_vel
    closing_speed = np.dot(rel_pos, traj_vel) / dist
    if closing_speed >= 0:  # distance not shrinking - no correction needed
        return None

    vel_norm = np.linalg.norm(traj_vel)
    if vel_norm < 1e-6:
        return None
    t_closest = -np.dot(rel_pos, traj_vel) / (vel_norm**2)
    if not (0 < t_closest < TIME_HORIZON):
        return None

    closest_point = rel_pos + traj_vel * t_closest
    miss_dist = np.linalg.norm(closest_point)
    if miss_dist >= combined_radius:
        return None

    if miss_dist < 1e-6:
        normal = np.array([-rel_pos[1], rel_pos[0]]) / dist
    else:
        normal = closest_point / miss_dist
    penetration = combined_radius - miss_dist
    urgency = max(0.5, 1.0 - t_closest / TIME_HORIZON)
    # Push self away from the predicted close-approach point (opposite of normal, which
    # points from self toward that point).
    return -normal * penetration * urgency * 3.0


REPULSE_RADIUS = 1.4
REPULSE_STRENGTH = 1.1


def compute_safe_velocity(
    self_pos: np.ndarray,
    self_vel: np.ndarray,
    pref_vel: np.ndarray,
    neighbors: list[NeighborState],
    max_speed: float,
) -> np.ndarray:
    candidate = np.array(pref_vel, dtype=float)

    for n in neighbors:
        rel_pos = n.pos - self_pos
        combined_radius = AGENT_RADIUS + n.radius + SAFETY_MARGIN
        correction = _orca_half_plane_adjust(rel_pos, candidate, n.vel, combined_radius)
        if correction is not None:
            candidate = candidate + correction

    # Layer a simple potential-field repulsion under the anticipatory correction above:
    # a monotonic push-apart floor that does not depend on predicting a future closest
    # approach, so it still protects agents when the cone prediction under-reacts.
    for n in neighbors:
        rel_pos = n.pos - self_pos
        dist = np.linalg.norm(rel_pos)
        react_radius = AGENT_RADIUS + n.radius + REPULSE_RADIUS
        if 1e-6 < dist < react_radius:
            strength = REPULSE_STRENGTH * (1.0 / dist**2 - 1.0 / react_radius**2)
            candidate = candidate - (rel_pos / dist) * strength

    speed = np.linalg.norm(candidate)
    if speed > max_speed:
        candidate = candidate / speed * max_speed
    return candidate
