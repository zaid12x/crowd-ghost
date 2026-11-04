"""The Curator — deterministic advice from the queueing model. No LLM, no free text.

Every line is a template filled with numbers that trace to the Jackson/Erlang-C
model of the *current* layout (rooms, capacities, gamma). If the model says the
flow is fine, the Curator says so — with the number.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from app.model.jackson import NetworkConfig, analyze, solve_traffic
from app.optimize.objective import rooms_seen_mean


@dataclass
class CuratorLine:
    severity: str   # "ok" | "warn" | "alert"
    text: str


def _config_from_level(level_id: str, level: dict, status: dict) -> NetworkConfig:
    rooms = level["rooms"]
    P = np.array(level["P"], dtype=float)
    gamma = np.zeros(len(rooms))
    gamma[0] = float(status.get("gamma", level.get("gamma", 1.0)))
    mu = np.array([1.0 / max(r["dwell"], 1e-3) for r in rooms])
    caps = status.get("capacities") or [r["capacity"] for r in rooms]
    return NetworkConfig(gamma=gamma, mu=mu, c=np.array(caps, dtype=np.int64), P=P)


def room_ascii_graph(level: dict, status: dict) -> str:
    """ASCII room graph with arrows weighted by flow and rho per room."""
    cfg = _config_from_level(level["id"], level, status)
    try:
        stats = analyze(cfg)
        lam = solve_traffic(cfg.P, cfg.gamma)
        lines = [f"FLOW GRAPH (gamma={cfg.gamma.sum():.2f}/s, lambda entry={lam[0]:.2f}/s)", ""]
        for i, room in enumerate(level["rooms"]):
            s = stats[i]
            lines.append(f"[{room['name'].upper()}]  rho={s.rho:.2f}  Wq={s.wq:.1f}s  cap={int(cfg.c[i])}")
            lines.extend(_flow_lines(i, cfg, level))
        return "\n".join(lines)
    except ValueError:
        # Infeasible: no steady state exists, so print offered load (a = lambda/mu*c)
        # instead of a fake rho — same honesty, just the number the solver has.
        try:
            lam = solve_traffic(cfg.P, cfg.gamma)
        except ValueError:
            return "MODEL INFEASIBLE — TRAFFIC EQUATIONS HAVE NO SOLUTION"
        lines = [
            f"FLOW GRAPH (gamma={cfg.gamma.sum():.2f}/s, lambda entry={lam[0]:.2f}/s)",
            "NO STEADY STATE — SHOWING OFFERED LOAD a = lambda / (cap * mu)",
            "",
        ]
        for i, room in enumerate(level["rooms"]):
            a = lam[i] / max(cfg.c[i] * cfg.mu[i], 1e-9)
            flag = "  << OVERSUBSCRIBED" if a >= 1 else ""
            lines.append(f"[{room['name'].upper()}]  a={a:.2f}  cap={int(cfg.c[i])}{flag}")
            lines.extend(_flow_lines(i, cfg, level))
        return "\n".join(lines)


def _flow_lines(i: int, cfg: NetworkConfig, level: dict) -> list[str]:
    lines = []
    for j, p in enumerate(cfg.P[i]):
        if p > 0.01:
            lines.append(f"    |--{p * 100:4.0f}%--> {level['rooms'][j]['name'].upper()}")
    rem = 1.0 - cfg.P[i].sum()
    if rem > 0.01:
        lines.append(f"    |--{rem * 100:4.0f}%--> EXIT")
    return lines


def advice(level_id: str, level: dict, status: dict) -> list[CuratorLine]:
    lines: list[CuratorLine] = []
    rooms = level["rooms"]
    cfg = _config_from_level(level_id, level, status)
    try:
        stats = analyze(cfg)
    except ValueError:
        worst_idx = 0
        # infeasible: identify the overloaded room by raw ratio
        lam = solve_traffic(cfg.P, cfg.gamma)
        ratios = [lam[i] / (cfg.c[i] * cfg.mu[i]) for i in range(len(lam))]
        worst_idx = int(np.argmax(ratios))
        lines.append(CuratorLine(
            "alert",
            f"{rooms[worst_idx]['name'].upper()} IS OVER CAPACITY. RHO={ratios[worst_idx]:.2f} -- QUEUE GROWS WITHOUT BOUND. ADD CAPACITY OR THROTTLE ENTRY.",
        ))
        return lines

    worst_i = int(np.argmax([s.rho for s in stats]))
    worst = stats[worst_i]
    worst_name = rooms[worst_i]["name"].upper()

    if worst.rho < 0.5:
        lines.append(CuratorLine("ok", f"FLOW IS NOMINAL. WORST ROOM {worst_name} AT RHO {worst.rho:.2f}. NO QUEUE FORMING."))
    elif worst.rho < 0.85:
        lines.append(CuratorLine("warn", f"{worst_name} TRENDING HOT: RHO {worst.rho:.2f}. WAIT {worst.wq:.1f}s EXPECTED. WATCH CAPACITY."))
    else:
        if worst.wq < 5.0:
            lines.append(CuratorLine("alert", f"{worst_name} AT RHO {worst.rho:.2f} (>0.85). NO WAIT YET ({worst.wq:.1f}s) BUT ZERO HEADROOM — ANY SURGE TIPS IT."))
        else:
            lines.append(CuratorLine("alert", f"{worst_name} AT RHO {worst.rho:.2f} (>0.85). EXPECTED WAIT {worst.wq:.1f}s. QUEUE IS SELF-FEEDING."))

    # what would help most? try 1.5x/2x/3x capacity on the worst room — model-checked.
    # Cheapest factor that recovers ~the best possible delta wins (no 3x waste).
    if worst.rho > 0.5:
        base_wq = worst.wq
        trials = []
        for factor in (1.5, 2.0, 3.0):
            trial_caps = [int(c) for c in cfg.c]
            trial_caps[worst_i] = max(int(trial_caps[worst_i] * factor), int(trial_caps[worst_i]) + 2)
            trial = NetworkConfig(gamma=cfg.gamma, mu=cfg.mu, c=np.array(trial_caps, dtype=np.int64), P=cfg.P)
            try:
                tstats = analyze(trial)
            except ValueError:
                continue
            trials.append((factor, trial_caps[worst_i], tstats[worst_i], base_wq - tstats[worst_i].wq))
        best = None
        if trials:
            max_delta = max(t[3] for t in trials)
            affordable = [t for t in trials if t[3] >= 0.95 * max_delta]
            best = sorted(affordable, key=lambda t: t[0])[0] if affordable else max(trials, key=lambda t: t[3])
        if best and best[3] > 0.05:
            factor, new_cap, tstats, delta = best
            lines.append(CuratorLine(
                "warn",
                f"FIX: {worst_name} CAPACITY {int(cfg.c[worst_i])} -> {int(new_cap)} (+{int(new_cap - cfg.c[worst_i])}). MODEL PREDICTS WAIT {base_wq:.1f}s -> {tstats.wq:.1f}s (-{delta:.1f}s).",
            ))

    # entry pressure
    lam0 = cfg.gamma.sum()
    if lam0 > 0 and worst.rho > 0.6:
        trial_gamma = cfg.gamma * 0.8
        trial_cfg = NetworkConfig(gamma=trial_gamma, mu=cfg.mu, c=cfg.c, P=cfg.P)
        try:
            trial_stats = analyze(trial_cfg)
            trial_rho = max(trial_stats[i].rho for i in range(len(trial_stats)))
            lines.append(CuratorLine(
                "warn",
                f"ENTRY AT {lam0:.2f}/s. THROTTLING TO {lam0 * 0.8:.2f}/s PREDICTS WORST RHO {trial_rho:.2f} (ERLANG C, RE-SOLVED).",
            ))
        except ValueError:
            lines.append(CuratorLine(
                "warn",
                f"ENTRY AT {lam0:.2f}/s ALREADY OVERSUBSCRIBES THE MODEL. NO STEADY STATE — THROTTLE ENTRY.",
            ))

    if cfg.gamma.sum() > 0:
        seen = rooms_seen_mean(cfg.P, cfg.gamma)
        lines.append(CuratorLine("ok", f"ROOMS SEEN PER VISITOR: {seen:.2f}. BUILD FLOW, NOT JUST WALLS."))
    else:
        lines.append(CuratorLine("ok", "ZERO ENTRY FLOW — NOTHING TO QUEUE. EVACUATION DRAINS BY EXIT CHAIN."))
    return lines
