"""Stage 3 gate tests: no wall tunnelling, determinism, capacity queue, tick budget."""

import json
import time
from pathlib import Path

import numpy as np

from app.physics.floorplan import Floorplan
from app.physics.social_force import PhysicsEngine, DT

LEVELS = Path(__file__).resolve().parent.parent / "data" / "levels"


def load(level_id):
    with open(LEVELS / f"{level_id}.json", "r", encoding="utf-8") as f:
        return json.load(f)


def run(level_id, seconds, seed=7, max_agents=None):
    level = load(level_id)
    eng = PhysicsEngine(level, seed=seed, max_agents=max_agents)
    ticks = int(seconds / DT)
    for _ in range(ticks):
        eng.step(DT)
    return eng


def test_no_wall_tunnelling_bottleneck():
    eng = run("bottleneck", 40.0, seed=11)
    fp = eng.fp
    pts = np.array([[a.x, a.y] for a in eng.agents])
    violations = ~fp.mask_inside(pts)
    assert violations.sum() == 0, f"{violations.sum()} agents outside valid space"


def test_no_wall_tunnelling_rush():
    eng = run("rush", 40.0, seed=13)
    fp = eng.fp
    pts = np.array([[a.x, a.y] for a in eng.agents])
    violations = ~fp.mask_inside(pts)
    assert violations.sum() == 0, f"{violations.sum()} agents outside valid space"


def test_deterministic_same_seed():
    a = run("lobby", 6.0, seed=99)
    b = run("lobby", 6.0, seed=99)
    pa = sorted((round(a.x, 6), round(a.y, 6)) for a in a.agents)
    pb = sorted((round(b.x, 6), round(b.y, 6)) for b in b.agents)
    assert pa == pb


def test_capacity_enforced_and_queue_forms():
    eng = run("bottleneck", 60.0, seed=7, max_agents=120)
    occ = eng.occupancy()
    assert occ[1] <= 6, f"hot exhibit over capacity: {occ[1]}"
    assert eng.peak_waiting > 0, "expected a queue at the hot exhibit door"


def test_agents_spawn_and_churn():
    eng = run("lobby", 30.0, seed=5)
    assert eng.spawned > 5


def test_tick_time_budget():
    level = load("rush")
    eng = PhysicsEngine(level, seed=7, max_agents=250)
    # warm up to populate
    for _ in range(int(30 / DT)):
        eng.step(DT)
    n = len(eng.agents)
    t0 = time.perf_counter()
    ticks = 90
    for _ in range(ticks):
        eng.step(DT)
    elapsed = time.perf_counter() - t0
    ms_per_tick = elapsed / ticks * 1000
    print(f"agents={n} ms/tick={ms_per_tick:.2f}")
    assert ms_per_tick < 50, f"tick too slow: {ms_per_tick:.2f} ms"
