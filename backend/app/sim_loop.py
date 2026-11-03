"""Authoritative simulation state.

Stage 1: dummy random-walk agents bouncing in a box, so the wire protocol
and frontend rendering can be verified end to end. Stage 3 swaps the dummy
update for the social-force physics model without changing the protocol.
"""

import numpy as np

from app.protocol import encode_frame

TICK_HZ = 30
DT = 1.0 / TICK_HZ


class SimState:
    def __init__(self, n_agents: int = 60, bounds=(40.0, 30.0), seed: int = 7):
        self.bounds = bounds
        self.rng = np.random.default_rng(seed)
        self.tick = 0
        self.n_rooms = 0
        self.flags = 0
        self.rooms = np.zeros((0, 3), dtype=np.float32)  # queue_len, rho, wait_est
        self.reset(n_agents)

    def reset(self, n_agents: int | None = None):
        if n_agents is None:
            n_agents = len(self.agents) if hasattr(self, "agents") else 60
        w, h = self.bounds
        rng = self.rng
        self.agents = np.column_stack([
            rng.uniform(1.0, w - 1.0, n_agents),
            rng.uniform(1.0, h - 1.0, n_agents),
            rng.uniform(-1.0, 1.0, n_agents) * 1.3,
            rng.uniform(-1.0, 1.0, n_agents) * 1.3,
        ]).astype(np.float32)
        speed = np.linalg.norm(self.agents[:, 2:4], axis=1, keepdims=True) + 1e-6
        self.agents[:, 2:4] *= 1.3 / speed
        self.tick = 0

    def update(self, dt: float = DT):
        w, h = self.bounds
        self.agents[:, 0:2] += self.agents[:, 2:4] * dt
        # bounce off walls
        for axis, limit in ((0, w), (1, h)):
            pos = self.agents[:, axis]
            vel = self.agents[:, axis + 2]
            lo = pos < 0.3
            hi = pos > limit - 0.3
            vel[lo] = np.abs(vel[lo])
            vel[hi] = -np.abs(vel[hi])
            pos[lo] = 0.3
            pos[hi] = limit - 0.3
        self.tick += 1

    def room_stats(self) -> np.ndarray:
        return self.rooms

    def frame(self) -> bytes:
        return encode_frame(self.tick, self.agents, self.room_stats(), self.flags)
