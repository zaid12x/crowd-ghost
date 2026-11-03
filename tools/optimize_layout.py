"""Stage 6: optimize museum layout per level.

Method: DES-ranked random search over (entry cap, capacities, routing nudge,
bottleneck door width), analytical metrics as diagnostics, physics sim to
re-check finalists (default vs naive vs optimizer).

Writes results/optimizer.json with everything, wins and losses.
"""
import argparse
import copy
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.model.jackson import NetworkConfig, analyze
from app.optimize.objective import try_metrics
from app.optimize.search import build_config, des_wait, candidate_id, apply_candidate_to_level
from app.physics.social_force import PhysicsEngine, DT

LEVELS = ["bottleneck", "lobby", "rush"]
T_END = {"bottleneck": 45.0, "lobby": 120.0, "rush": 40.0}
N_CANDIDATES = 240


def load_level(name):
    with open(ROOT / "backend" / "data" / "levels" / f"{name}.json", "r", encoding="utf-8") as f:
        return json.load(f)


def default_candidate(level):
    return {
        "entry_cap": float(level["gamma"]),
        "capacities": [r["capacity"] for r in level["rooms"]],
        "routing_delta": {},
        "widths": {},
        "label": "default",
    }


def naive_candidate(level):
    n = len(level["rooms"])
    total = sum(r["capacity"] for r in level["rooms"])
    base = total // n
    caps = [base] * n
    caps[0] += total - base * n  # remainder to lobby
    return {
        "entry_cap": float(level["gamma"]),
        "capacities": caps,
        "routing_delta": {},
        "widths": {},
        "label": "naive (equal capacities)",
    }


def candidate_space(level, seed=0):
    rng = np.random.default_rng(seed)
    rooms = level["rooms"]
    n = len(rooms)
    default_caps = [r["capacity"] for r in rooms]
    total_cap = sum(default_caps)
    default_gamma = float(level["gamma"])
    yield default_candidate(level)
    yield naive_candidate(level)

    # which door is the bottleneck? widen it, shrink the entrance by the same amount
    hot_idx = int(np.argmin([r["capacity"] / max(r.get("dwell", 1), 1e-3) for r in rooms]))
    hot_door = next((d for d in level["doors"] if d.get("rooms") and rooms[d["rooms"][1] or 0]["id"] == hot_idx or d["rooms"][0] == hot_idx), None)
    entrance = next(d for d in level["doors"] if d["rooms"][0] is None)
    bottleneck_door = next(d for d in level["doors"] if len(d["rooms"]) >= 2 and (d["rooms"][0] == hot_idx or d["rooms"][1] == hot_idx) and entrance is not None)
    bd_width = bottleneck_door["width"]

    for _ in range(N_CANDIDATES):
        mult = float(rng.choice([0.7, 0.8, 0.9, 1.0, 1.15]))  # floor: museum keeps >=70% of footfall
        entry = max(0.4, default_gamma * mult)

        weights = rng.lognormal(0.0, 0.45, n)
        caps = np.maximum(1, np.floor(total_cap * weights / weights.sum()).astype(int))
        # adjust to exact budget
        diff = total_cap - int(caps.sum())
        while diff != 0:
            idx = int(np.argmax(weights if diff > 0 else 1 / weights))
            if diff > 0:
                caps[idx] += 1
                diff -= 1
            else:
                if caps[idx] > 1:
                    caps[idx] -= 1
                    diff += 1
                else:
                    weights[idx] = 1e-9

        delta = float(rng.choice([-0.15, -0.075, 0.0, 0.075, 0.15]))
        routing_delta = {0: delta} if delta != 0.0 else {}

        cand = {
            "entry_cap": entry,
            "capacities": [int(c) for c in caps],
            "routing_delta": routing_delta,
            "widths": {},
            "label": "search",
        }
        # widen the bottleneck door if we have budget room elsewhere (entrance compensates)
        if bottleneck_door is not None:
            widen = float(rng.choice([0.0, 0.5, 1.0, 1.6]))
            if widen > 0 and entrance is not None:
                new_bd = min(bd_width + widen, 3.4)
                new_ent = max(1.2, entrance["width"] - (new_bd - bd_width))
                cand["widths"] = {bottleneck_door["id"]: new_bd, entrance["id"]: new_ent}
        yield cand


def des_eval(level, cand):
    cfg = build_config(level, cand)
    from app.model.jackson import solve_traffic
    wq = des_wait(cfg, reps=6, t_end=T_END[level["id"]], base_seed=4242)
    try:
        metrics = try_metrics(cfg)
    except Exception:
        metrics = {"feasible": False, "score": float("inf")}
    return wq, metrics


def physics_eval(level, cand, seconds=50.0, seed=99):
    lvl = apply_candidate_to_level(level, cand)
    eng = PhysicsEngine(lvl, seed=seed)
    ticks = int(seconds / DT)
    t0 = time.perf_counter()
    for _ in range(ticks):
        eng.step(DT)
    return {
        "mean_queue_s_per_exit": eng.mean_queue_seconds_per_exit(),
        "exited": eng.exited,
        "spawned": eng.spawned,
        "peak_waiting": eng.peak_waiting,
        "wall_s": time.perf_counter() - t0,
    }


def optimize_level(name, reps_search=True):
    level = load_level(name)
    level = {**level, "id": name}
    print(f"\n=== {level.get('name', name)} ===")
    t0 = time.time()

    scored = []
    for i, cand in enumerate(candidate_space(level, seed=17)):
        wq, metrics = des_eval(level, cand)
        scored.append({"cand": cand, "des_wait": wq, "metrics": metrics})
        if (i + 1) % 60 == 0:
            best = min(s["des_wait"] for s in scored)
            print(f"  eval {i + 1}: best des_wait={best:.3f}s")

    scored.sort(key=lambda s: s["des_wait"])
    default_r = next(s for s in scored if s["cand"]["label"] == "default")
    naive_r = next(s for s in scored if s["cand"]["label"] == "naive (equal capacities)")
    best = scored[0]

    # physics re-check: default, naive, best-by-DES, and best-by-DES with widths zeroed
    phys = {}
    for label, cand in [("default", default_r["cand"]), ("naive", naive_r["cand"]), ("optimized", best["cand"])]:
        phys[label] = physics_eval(level, cand, seconds=50.0, seed=99)
        p = phys[label]
        print(f"  physics[{label}] queue_s/exit={p['mean_queue_s_per_exit']:.2f}s exited={p['exited']} peak_wait={p['peak_waiting']}")

    print(f"  des_wait: default={default_r['des_wait']:.3f}s naive={naive_r['des_wait']:.3f}s optimized={best['des_wait']:.3f}s")

    def pct(new, old):
        return (old - new) / old * 100 if old else 0.0

    return {
        "level": name,
        "name": level.get("name", name),
        "seconds_search": time.time() - t0,
        "search": {"candidates": len(scored), "des_reps": 6, "t_end": T_END[name]},
        "default": {
            "des_wait": default_r["des_wait"],
            "des_feasible": default_r["metrics"].get("feasible", False),
            "rho_max": default_r["metrics"].get("rho_max"),
            "physics": phys["default"],
            "candidate": default_r["cand"],
        },
        "naive": {
            "des_wait": naive_r["des_wait"],
            "des_feasible": naive_r["metrics"].get("feasible", False),
            "rho_max": naive_r["metrics"].get("rho_max"),
            "physics": phys["naive"],
            "candidate": naive_r["cand"],
        },
        "optimized": {
            "des_wait": best["des_wait"],
            "des_feasible": best["metrics"].get("feasible", False),
            "rho_max": best["metrics"].get("rho_max"),
            "physics": phys["optimized"],
            "candidate": best["cand"],
            "candidate_id": candidate_id(best["cand"]),
        },
        "improvement_vs_default_pct_des": pct(best["des_wait"], default_r["des_wait"]),
        "improvement_vs_naive_pct_des": pct(best["des_wait"], naive_r["des_wait"]),
        "improvement_vs_default_pct_physics_queue": pct(phys["optimized"]["mean_queue_s_per_exit"], phys["default"]["mean_queue_s_per_exit"]),
        "improvement_vs_naive_pct_physics_queue": pct(phys["optimized"]["mean_queue_s_per_exit"], phys["naive"]["mean_queue_s_per_exit"]),
        "beats_default_des": best["des_wait"] < default_r["des_wait"],
        "beats_naive_des": best["des_wait"] < naive_r["des_wait"],
        "beats_default_physics": phys["optimized"]["mean_queue_s_per_exit"] < phys["default"]["mean_queue_s_per_exit"],
        "beats_naive_physics": phys["optimized"]["mean_queue_s_per_exit"] < phys["naive"]["mean_queue_s_per_exit"],
        "top5": [
            {
                "candidate_id": candidate_id(s["cand"]),
                "des_wait": s["des_wait"],
                "feasible": s["metrics"].get("feasible", False),
            }
            for s in scored[:5]
        ],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--levels", default=",".join(LEVELS))
    ap.add_argument("--out", default=str(ROOT / "results" / "optimizer.json"))
    args = ap.parse_args()
    names = [s.strip() for s in args.levels.split(",")]

    results = [optimize_level(n) for n in names]
    out = {"levels": results}
    Path(args.out).write_text(json.dumps(out, indent=2))
    print(f"\noptimizer results -> {args.out}")
    for r in results:
        print(
            f"{r['level']:<12} beats default: DES {'Y' if r['beats_default_des'] else 'n'} "
            f"physics {'Y' if r['beats_default_physics'] else 'n'} | "
            f"beats naive: DES {'Y' if r['beats_naive_des'] else 'n'} "
            f"physics {'Y' if r['beats_naive_physics'] else 'n'} | "
            f"wait {r['improvement_vs_default_pct_des']:+.1f}% vs default"
        )


if __name__ == "__main__":
    main()
