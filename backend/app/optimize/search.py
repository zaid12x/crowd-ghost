"""Layout search: analytical pre-score (where feasible), DES for real ranking,
physics to re-check the finalists.

Decision variables per level (4):
  1. entry_cap       — spawn rate cap (persons/second)        [0.4x .. 1.3x default]
  2. capacities      — per-room c_i, budget-neutral           [jitter around default]
  3. door widths     — one widened door compensated elsewhere [bottleneck door]
  4. routing nudge   — shift flow between optional routes     [±0.15]
"""

from __future__ import annotations

import copy

import numpy as np

from app.model import des
from app.model.jackson import NetworkConfig
from app.optimize.objective import try_metrics

RATE_SCALE = 1.0  # level units are per second; DES/model are unit-agnostic


def build_config(level: dict, cand: dict) -> NetworkConfig:
    rooms = level["rooms"]
    n = len(rooms)
    P = np.array(level.get("P", np.eye(n)), dtype=float).copy()
    for row, delta in cand.get("routing_delta", {}).items():
        row = int(row)
        nz = [j for j in range(n) if P[row][j] > 0 and j != np.argmax(P[row])]
        if not nz:
            continue
        src = int(np.argmax(P[row]))
        dst = nz[0]
        delta = float(np.clip(delta, -0.15, 0.15))
        new_src = P[row][src] + delta
        new_dst = P[row][dst] - delta
        if new_src >= 0.0 and new_dst >= 0.0:
            P[row][src], P[row][dst] = new_src, new_dst
    gamma = np.zeros(n)
    gamma[0] = min(float(level.get("gamma", 1.0)), float(cand["entry_cap"]))
    mu = np.array([1.0 / max(r["dwell"], 1e-3) for r in rooms])
    capacities = np.array(cand["capacities"], dtype=np.int64)
    return NetworkConfig(gamma=gamma, mu=mu, c=capacities, P=P)


def apply_candidate_to_level(level: dict, cand: dict) -> dict:
    """Clone the level dict with candidate door widths + capacities."""
    lvl = copy.deepcopy(level)
    lvl["gamma"] = min(float(level.get("gamma", 1.0)), float(cand["entry_cap"]))
    for i, room in enumerate(lvl["rooms"]):
        room["capacity"] = int(cand["capacities"][i])
    for door in lvl["doors"]:
        if door["id"] in cand.get("widths", {}):
            door["width"] = float(cand["widths"][door["id"]])
    return lvl


def des_wait(cfg: NetworkConfig, reps: int = 6, t_end: float = 40.0, base_seed: int = 4242) -> float:
    """Lambda-weighted mean queue wait across replications (per-second units)."""
    lam_cache = {}
    from app.model.jackson import solve_traffic

    lam = solve_traffic(cfg.P, cfg.gamma)
    lam_total = max(float(lam.sum()), 1e-9)
    waits = []
    for rep in range(reps):
        res = des.run(cfg, seed=base_seed + rep, t_end=t_end, warm_up_frac=0.15)
        wq_rep = sum(lam[i] / lam_total * res[i]["mean_wait"] for i in range(len(lam)))
        waits.append(wq_rep)
    return float(np.mean(waits))


def candidate_id(cand: dict) -> str:
    cap = ",".join(str(int(c)) for c in cand["capacities"])
    return f"cap=[{cap}] entry={cand['entry_cap']:.2f} widths={cand.get('widths', {})} nudge={cand.get('routing_delta', {})}"
