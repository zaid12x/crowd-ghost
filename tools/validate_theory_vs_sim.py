"""Stage 2 gate: analytical Jackson model vs discrete-event simulation.

Three configs (light / medium / near-saturation), 30 DES replications each.
Reports per-room mean queue wait: theory (Erlang C via Jackson solve) vs
DES mean with 95% CI. Saves results/theory_vs_sim.png + .json.

Gate criteria:
  - light & medium: theory Wq must fall inside each room's 95% CI
  - near-saturation: |theory - sim| / theory <= 10% per room
"""

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.model.jackson import NetworkConfig, analyze
from app.model import des

ROOM_NAMES = ["Lobby", "Gallery A", "Gallery B", "Gift Shop"]

# Lobby -> Gallery A -> (0.9) Gallery B -> (0.8) Gift Shop -> exit
P = np.array([
    [0.0, 1.0, 0.0, 0.0],
    [0.0, 0.0, 0.9, 0.0],
    [0.0, 0.0, 0.0, 0.8],
    [0.0, 0.0, 0.0, 0.0],
])
MU = np.array([1.0, 1.0, 1.0, 1.0])
# Gate configs use c=1 everywhere: Burke's theorem makes inter-room flows
# Poisson, so the Jackson/Erlang-C theory is EXACT here by construction.
# (Erlang-C multi-server correctness is covered by unit tests.)
C_SINGLE = np.array([1, 1, 1, 1])
# Informational only: c=2 lobby -> non-Poisson flow into Gallery A, so the
# theory is a planning approximation there (see PLAN.md risks table).
C_LOBBY2 = np.array([2, 1, 1, 1])

CONFIGS = {
    "light": (np.array([0.4, 0.0, 0.0, 0.0]), C_SINGLE, True),
    "medium": (np.array([0.7, 0.0, 0.0, 0.0]), C_SINGLE, True),
    "near_saturation": (np.array([0.9, 0.0, 0.0, 0.0]), C_SINGLE, True),
    "lobby_2servers (info)": (np.array([0.7, 0.0, 0.0, 0.0]), C_LOBBY2, False),
}

REPLICATIONS = 30  # per PLAN.md; t_end sized for ~12000 customers per rep


def run_config(name: str, gamma: np.ndarray, c: np.ndarray, reps: int) -> dict:
    cfg = NetworkConfig(gamma=gamma, mu=MU, c=c, P=P)
    theory = analyze(cfg)
    sim_waits = [[] for _ in range(len(gamma))]
    meta = None
    for rep in range(reps):
        res = des.run(cfg, seed=1000 + rep)
        meta = res["_meta"]
        for i in range(len(gamma)):
            sim_waits[i].append(res[i]["mean_wait"])

    rows = []
    for i in range(len(gamma)):
        samples = np.array(sim_waits[i])
        mean = float(samples.mean())
        ci = float(stats.t.interval(0.95, len(samples) - 1, loc=mean, scale=stats.sem(samples))[1] - mean)
        rows.append({
            "room": ROOM_NAMES[i],
            "theory_wq": float(theory[i].wq),
            "sim_mean": mean,
            "sim_ci95": ci,
            "inside_ci": bool(abs(mean - theory[i].wq) <= ci),
            "rel_err": float(abs(mean - theory[i].wq) / theory[i].wq) if theory[i].wq > 1e-12 else 0.0,
            "rho": float(theory[i].rho),
            "customers": int(res[i]["customers"]),
        })
    return {"config": name, "gamma": gamma.tolist(), "t_end": meta["t_end"], "reps": reps, "rooms": rows}


def main():
    out_dir = Path(__file__).resolve().parent.parent / "results"
    out_dir.mkdir(exist_ok=True)

    all_results = []
    gate_pass = True
    print(f"{'config':<22}{'room':<12}{'rho':>6}{'theory':>10}{'sim':>10}{'ci95':>8}{'verdict':>8}")
    print("-" * 76)
    for name, (gamma, c, is_gate) in CONFIGS.items():
        res = run_config(name, gamma, c, REPLICATIONS)
        res["is_gate"] = is_gate
        all_results.append(res)
        for row in res["rooms"]:
            if not is_gate:
                ok = None  # informational; not pass/fail
            elif name == "near_saturation":
                ok = row["rel_err"] <= 0.10
            else:
                ok = row["inside_ci"]
            if ok is not None:
                gate_pass = gate_pass and ok
            verdict = "INFO" if ok is None else ("PASS" if ok else "FAIL")
            print(f"{name:<22}{row['room']:<12}{row['rho']:>6.2f}{row['theory_wq']:>10.3f}{row['sim_mean']:>10.3f}{row['sim_ci95']:>8.3f}{verdict:>8}")

    # plot
    fig, axes = plt.subplots(1, len(CONFIGS), figsize=(14, 4.5), sharey=False)
    for ax, res in zip(axes, all_results):
        x = np.arange(len(res["rooms"]))
        tw = [r["theory_wq"] for r in res["rooms"]]
        sw = [r["sim_mean"] for r in res["rooms"]]
        ci = [r["sim_ci95"] for r in res["rooms"]]
        ax.bar(x - 0.2, tw, 0.35, label="theory (Erlang C)", color="#39ff14", alpha=0.85)
        ax.bar(x + 0.2, sw, 0.35, yerr=ci, capsize=4, label="DES mean ±95% CI", color="#ffb000", alpha=0.85)
        ax.set_xticks(x)
        ax.set_xticklabels([r["room"] for r in res["rooms"]], rotation=20, ha="right", fontsize=8)
        ax.set_title(f"{res['config']}  (t_end={res['t_end']:.0f}m, reps={res['reps']})", fontsize=9)
        ax.set_ylabel("mean queue wait (min)")
        ax.grid(axis="y", alpha=0.3)
    axes[0].legend(fontsize=8)
    fig.suptitle("CROWD GHOST — Jackson model vs DES")
    fig.tight_layout()
    fig.savefig(out_dir / "theory_vs_sim.png", dpi=140)

    payload = {"gate": "PASS" if gate_pass else "FAIL", "configs": all_results}
    (out_dir / "theory_vs_sim.json").write_text(json.dumps(payload, indent=2))
    print("-" * 76)
    print("GATE:", "PASS" if gate_pass else "FAIL")
    print(f"plot: {out_dir / 'theory_vs_sim.png'}")
    sys.exit(0 if gate_pass else 1)


if __name__ == "__main__":
    main()
