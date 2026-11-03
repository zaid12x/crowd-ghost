"""Authoritative simulation state.

Stage 3: physics-backed crowd engine (social force). Stage 1's dummy
random-walkers are gone; protocol and tick rate are unchanged.
"""

import json
import os
from pathlib import Path

import numpy as np

from app.physics.social_force import PhysicsEngine, DT as ENGINE_DT
from app.protocol import encode_frame

TICK_HZ = 30
DT = 1.0 / TICK_HZ

LEVELS_DIR = Path(__file__).resolve().parent.parent / "data" / "levels"
DEFAULT_LEVEL = os.environ.get("CROWD_GHOST_LEVEL", "lobby")


def level_path(level_id: str) -> Path:
    p = LEVELS_DIR / f"{level_id}.json"
    if not p.is_file():
        raise FileNotFoundError(f"unknown level '{level_id}' (looked in {p})")
    return p


def load_level(level_id: str) -> dict:
    with open(level_path(level_id), "r", encoding="utf-8") as f:
        return json.load(f)


class SimState:
    def __init__(self, level_id: str | None = None, seed: int = 7):
        self.level_id = level_id or DEFAULT_LEVEL
        self.seed = seed
        self.reload(self.level_id)

    def reload(self, level_id: str, seed: int | None = None):
        level = load_level(level_id)
        self.level_id = level_id
        self.level = level
        self.engine = PhysicsEngine(level, seed=self.seed if seed is None else seed)
        self.bounds = tuple(level["bounds"])

    def update(self, dt: float = DT):
        self.engine.step(dt)

    @property
    def tick(self) -> int:
        return int(self.engine.time * TICK_HZ)

    def frame(self) -> bytes:
        agents, rooms = self.engine.frame_arrays()
        return encode_frame(self.tick, agents, rooms, flags=(1 if self.engine.evacuation else 0))

    def status(self) -> dict:
        return {
            "level": self.level_id,
            "name": self.level.get("name", self.level_id),
            "bounds": list(self.bounds),
            "agents": len(self.engine.agents),
            "spawned": self.engine.spawned,
            "exited": self.engine.exited,
            "waiting": self.engine.waiting_total,
            "peak_waiting": self.engine.peak_waiting,
            "tick": self.tick,
            "evacuation": self.engine.evacuation,
        }
