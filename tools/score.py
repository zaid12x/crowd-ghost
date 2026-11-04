"""Score every level from fresh straight runs (seed 7), and write results/scores.json.

Mean wait and crush fraction are MEASURED from the physics sim — never model
predictions. rooms_seen comes from the Markov routing (model, labeled as such).
Evacuation levels report time-to-clear instead of a queueing score.

Usage: python tools/score.py [level ...]     (default: all five, ~3-4 min)
"""

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.optimize.objective import rooms_seen_mean
from app.physics.social_force import DT, PhysicsEngine
from app.scoring import crush_fraction, score_queueing
from app.sim_loop import load_level

LEVELS = ["lobby", "rush", "bottleneck", "firedrill", "realfootage"]
SIM_SECONDS = 90.0
MAX_EVAC_SECONDS = 240.0


def run(level_id: str) -> dict:
    level = load_level(level_id)
    eng = PhysicsEngine(level, seed=7)
    if level.get("evacuation"):
        while eng.agents and eng.time < MAX_EVAC_SECONDS:
            eng.step(DT)
        return {
            "kind": "evacuation",
            "time_to_clear_s": round(eng.time, 2) if not eng.agents else None,
            "spawned": eng.spawned,
            "exited": eng.exited,
            "agents_left": len(eng.agents),
            "crush_frac": round(crush_fraction(eng.crush_seconds, eng.agent_seconds), 4),
        }
    ticks = int(SIM_SECONDS / DT)
    for _ in range(ticks):
        eng.step(DT)
    gamma = np.zeros(len(eng.fp.rooms))
    gamma[0] = float(eng.gamma)
    rooms_seen = float(rooms_seen_mean(np.array(level["P"], dtype=float), gamma))
    mean_wait = float(eng.mean_queue_seconds_per_exit())
    crush = crush_fraction(eng.crush_seconds, eng.agent_seconds)
    return {
        "kind": "queue",
        "mean_wait_s": round(mean_wait, 3),
        "crush_frac": round(crush, 4),
        "rooms_seen": round(rooms_seen, 2),
        "score": score_queueing(mean_wait, crush, rooms_seen),
        "spawned": eng.spawned,
        "exited": eng.exited,
        "peak_waiting": eng.peak_waiting,
    }


if __name__ == "__main__":
    only = sys.argv[1:] or LEVELS
    out: dict[str, dict] = {}
    for lv in only:
        out[lv] = run(lv)
        print(lv, json.dumps(out[lv]))
    (ROOT / "results" / "scores.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("\nwrote results/scores.json")
