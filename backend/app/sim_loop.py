"""Authoritative simulation state.

Stage 3: physics-backed crowd engine (social force). Stage 1's dummy
random-walkers are gone; protocol and tick rate are unchanged.
"""

import copy
import json
import os
from pathlib import Path

import numpy as np

from app.physics.social_force import PhysicsEngine, DT as ENGINE_DT
from app.protocol import encode_frame

TICK_HZ = 30
DT = 1.0 / TICK_HZ

LEVELS_DIR = Path(__file__).resolve().parent.parent / "data" / "levels"
ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_LEVEL = os.environ.get("CROWD_GHOST_LEVEL", "lobby")


def level_path(level_id: str) -> Path:
    p = LEVELS_DIR / f"{level_id}.json"
    if not p.is_file():
        raise FileNotFoundError(f"unknown level '{level_id}' (looked in {p})")
    return p


def load_level(level_id: str) -> dict:
    with open(level_path(level_id), "r", encoding="utf-8") as f:
        return json.load(f)


FLAG_EVACUATION = 0x01
FLAG_SIDE_B = 0x02


class SimState:
    def __init__(self, level_id: str | None = None, seed: int = 7):
        self.level_id = level_id or DEFAULT_LEVEL
        self.seed = seed
        self.split = False
        self.reload(self.level_id)

    def reload(self, level_id: str, seed: int | None = None):
        level = load_level(level_id)
        self.level_id = level_id
        self.level = level
        self.engine = PhysicsEngine(level, seed=self.seed if seed is None else seed)
        self.engine_b: PhysicsEngine | None = None
        if self.split:
            self._build_optimized()
        self.bounds = tuple(level["bounds"])

    def _build_optimized(self):
        """Side B: same seed/level, optimizer's best-known layout for this level."""
        level = copy.deepcopy(self.level)
        opt = None
        try:
            opt = json.loads((ROOT / "results" / "optimizer.json").read_text())
            for lv in opt.get("levels", []):
                if lv["level"] == self.level_id:
                    opt = lv["optimized"]["candidate"]
                    break
            else:
                opt = None
        except Exception:
            opt = None
        if opt:
            level["gamma"] = opt["entry_cap"]
            for i, room in enumerate(level["rooms"]):
                room["capacity"] = int(opt["capacities"][i])
            for door in level["doors"]:
                if door["id"] in opt.get("widths", {}):
                    door["width"] = float(opt["widths"][door["id"]])
            # routing nudge applied to P if present
            for row, delta in opt.get("routing_delta", {}).items():
                row = int(row)
                nz = [j for j in range(len(level["P"][row])) if level["P"][row][j] > 0 and j != max(range(len(level["P"][row])), key=lambda j: level["P"][row][j])]
                if nz:
                    src = max(range(len(level["P"][row])), key=lambda j: level["P"][row][j])
                    dst = nz[0]
                    level["P"][row][src] += delta
                    level["P"][row][dst] -= delta
        self.engine_b = PhysicsEngine(level, seed=self.seed)

    def set_split(self, on: bool):
        self.split = bool(on)
        if self.split:
            self._build_optimized()
        else:
            self.engine_b = None

    def apply_params(self, params: dict):
        """Hot-reload parameters on engine A (sliders) without resetting the crowd."""
        eng = self.engine
        if "gamma_scale" in params:
            base = float(self.level.get("gamma", 1.0))
            eng.gamma = max(0.05, base * float(params["gamma_scale"]))
        for i, cap in enumerate(params.get("capacities", [])):
            if i < len(self.fp_rooms()):
                eng.fp.rooms[i].capacity = max(1, int(cap))
        for door_id, width in params.get("door_widths", {}).items():
            w = float(width)
            eng.door_rate[door_id] = w * 1.3
            eng.door_tokens[door_id] = max(eng.door_tokens.get(door_id, 0.0), w * 1.3)
            for door in eng.fp.doors:
                if door.id == door_id:
                    door.width = w
        return self.status()

    def fp_rooms(self):
        return self.engine.fp.rooms

    def update(self, dt: float = DT):
        self.engine.step(dt)
        if self.split and self.engine_b is not None:
            # Catch engine B up to engine A's elapsed time, budget-capped per
            # call so the sender never stalls for more than a few ms.
            steps = 0
            while self.engine_b.time < self.engine.time and steps < 240:
                self.engine_b.step(dt)
                steps += 1

    @property
    def tick(self) -> int:
        return int(self.engine.time * TICK_HZ)

    def frame(self, side_b: bool = False) -> bytes:
        if side_b and self.engine_b is not None:
            agents, rooms = self.engine_b.frame_arrays()
            return encode_frame(self.tick, agents, rooms, flags=FLAG_SIDE_B)
        agents, rooms = self.engine.frame_arrays()
        flags = FLAG_EVACUATION if self.engine.evacuation else 0
        return encode_frame(self.tick, agents, rooms, flags=flags)

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
            "split": self.split,
            "side_b_agents": len(self.engine_b.agents) if self.engine_b else 0,
            "gamma": self.engine.gamma,
            "capacities": [r.capacity for r in self.engine.fp.rooms],
            "door_widths": {d.id: d.width for d in self.engine.fp.doors},
        }
