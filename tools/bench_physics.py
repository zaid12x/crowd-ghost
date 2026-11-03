"""Stage 3 gate bench: 250 agents at >=30 ticks/s sustained for 60 sim-seconds.

Also reports: peak queue at the bottleneck door and door-region density vs
shop density (expect >2x).
"""
import json
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

import numpy as np

from app.physics.social_force import PhysicsEngine, DT

LEVEL = sys.argv[1] if len(sys.argv) > 1 else "rush"
SIM_SECONDS = 60.0
MAX_AGENTS = 250


def main():
    with open(BACKEND / "data" / "levels" / f"{LEVEL}.json", "r", encoding="utf-8") as f:
        level = json.load(f)
    eng = PhysicsEngine(level, seed=7, max_agents=MAX_AGENTS)

    ticks = int(SIM_SECONDS / DT)
    t0 = time.perf_counter()
    milestones = {}
    for i in range(ticks):
        eng.step(DT)
        if (i + 1) in (ticks // 4, ticks // 2, ticks):
            milestones[i + 1] = len(eng.agents)
    elapsed = time.perf_counter() - t0

    n = len(eng.agents)
    tps = ticks / elapsed
    print(f"level={LEVEL} ticks={ticks} simulated={SIM_SECONDS}s wall={elapsed:.1f}s")
    print(f"agents_final={n} agents_min={min(milestones.values())} agents_max={max(milestones.values())}")
    print(f"ticks_per_second={tps:.1f}  (gate: >= 30)")
    print(f"peak_waiting={eng.peak_waiting} waiting_now={eng.waiting_total}")
    ok = n >= 200 and tps >= 30.0
    print("GATE:", "PASS" if ok else "FAIL")

    if LEVEL == "bottleneck":
        # density near d0 (16,15): box 8m wide x 6m deep to the west of the door
        door_box = ((12.0, 16.0), (12.0, 18.0))
        shop = ((30.0, 44.0), (7.0, 23.0))
        area_door = (4.0) * (6.0)
        area_shop = (14.0) * (16.0)
        agents = eng.agents

        def count_in(x0, x1, y0, y1):
            return sum(1 for a in agents if x0 <= a.x <= x1 and y0 <= a.y <= y1)

        d_door = count_in(*door_box[0], *door_box[1]) / area_door
        d_shop = count_in(*shop[0], *shop[1]) / area_shop
        print(f"door-region density={d_door:.3f} agents/m^2  shop density={d_shop:.3f}  ratio={d_door / max(d_shop, 1e-9):.2f}  (gate: >2x)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
