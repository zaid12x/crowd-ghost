"""Objective function for layout search (documented weights).

Candidate layout -> weighted mean queue wait (Erlang C, Jackson network) +
overload penalty minus a small "rooms seen" bonus.

    score = mean_wait_weighted
          + ALPHA * sum_rho_overload     (per room above rho=0.85, in minutes * weight)
          - BETA  * mean_rooms_seen      (expected distinct rooms visited per customer)

Units: rates per SECOND (level units). The analytical score is only returned
for feasible networks (all rho < 1); otherwise the candidate is infeasible.
"""

from __future__ import annotations

import numpy as np

from app.model.jackson import NetworkConfig, analyze, solve_traffic

ALPHA = 3.0   # penalty per unit of rho beyond 0.85 (minutes per unit)
BETA = 0.6    # bonus per mean room seen (minutes)
RHO_SOFT = 0.85


def rooms_seen_mean(P: np.ndarray, gamma: np.ndarray) -> float:
    lam = solve_traffic(P, gamma)
    entry = max(float(gamma.sum()), 1e-9)
    return float(lam.sum() / entry)


def network_metrics(cfg: NetworkConfig) -> dict:
    stats = analyze(cfg)  # raises if infeasible
    lam = solve_traffic(cfg.P, cfg.gamma)
    lam_total = max(float(lam.sum()), 1e-9)
    wq = float(sum(s.lam * s.wq for s in stats) / lam_total)
    rho_max = max(s.rho for s in stats)
    overload = sum(max(0.0, s.rho - RHO_SOFT) for s in stats)
    seen = rooms_seen_mean(cfg.P, cfg.gamma)
    score = wq + ALPHA * overload - BETA * seen
    return {
        "feasible": True,
        "mean_wait": wq,
        "rho_max": rho_max,
        "overload": overload,
        "rooms_seen": seen,
        "score": score,
    }


def try_metrics(cfg: NetworkConfig) -> dict:
    try:
        return network_metrics(cfg)
    except ValueError:
        return {"feasible": False, "score": float("inf"), "rho_max": float("inf")}
