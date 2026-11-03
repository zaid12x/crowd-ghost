"""tracks.json + zone polygons -> estimated queueing parameters.

Outputs:
  lambda(t)  — entries into the entry zone per minute, EMA-smoothed, sampled at 1 Hz
  mu         — mean service rate per server per minute (from dwell in the service zone)
  P          — routing matrix between zones (row-normalised; remainder = exit)
  dwell      — mean dwell in the service zone (seconds) and p90
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np


def load_zones(path):
    with open(path, "r", encoding="utf-8") as f:
        z = json.load(f)

    def to_boxes(lst):
        return [tuple(b) for b in lst]

    return {
        "entry": to_boxes(z["entry"]),
        "service": to_boxes(z["service"]),
        "rooms": {k: to_boxes(v) for k, v in z["rooms"].items()},
    }


def in_boxes(x, y, boxes):
    for x0, y0, x1, y1 in boxes:
        if x0 <= x <= x1 and y0 <= y <= y1:
            return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tracks", required=True)
    ap.add_argument("--zones", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    with open(args.tracks, "r", encoding="utf-8") as f:
        data = json.load(f)
    zones = load_zones(args.zones)
    fps = data["fps"]

    room_names = list(zones["rooms"].keys())
    room_idx = {name: i for i, name in enumerate(room_names)}

    # per-track: room sequence and entry-zone event
    entry_events = []           # times (s) of first entry into entry zone
    transitions = np.zeros((len(room_names), len(room_names)))
    dwell_samples = []

    for track in data["tracks"]:
        pts = track["points"]
        entry_logged = False
        in_service_run = 0.0
        prev_t = None
        prev_room = None
        pending_room = None       # hysteresis: room switch only after 0.75 s inside
        pending_since = None
        for f_i, t, x, y in pts:
            raw = None
            for i, name in enumerate(room_names):
                if in_boxes(x, y, zones["rooms"][name]):
                    raw = name
                    break
            # hysteresis: switch rooms only after residing in the candidate for 0.75 s
            if raw == prev_room:
                pending_room = None
            elif raw == pending_room:
                if t - pending_since >= 0.75:
                    if prev_room is not None and raw is not None:
                        transitions[room_idx[prev_room], room_idx[raw]] += 1
                    prev_room = raw
                    pending_room = None
            else:
                pending_room = raw
                pending_since = t
            # entry zone
            if not entry_logged and in_boxes(x, y, zones["entry"]):
                entry_events.append(t)
                entry_logged = True
            # service zone dwell (time-weighted)
            if prev_t is not None:
                dt = t - prev_t
                if in_boxes(x, y, zones["service"]):
                    in_service_run += dt
                else:
                    if in_service_run > 0.5:
                        dwell_samples.append(in_service_run)
                    in_service_run = 0.0
            prev_t = t
        if in_service_run > 0.5:
            dwell_samples.append(in_service_run)

    # lambda(t): entries per minute (events), EMA smoothed, 1 Hz samples
    total_s = 0.0
    for track in data["tracks"]:
        if track["points"]:
            total_s = max(total_s, track["points"][-1][1])
    t_axis = np.arange(0, int(total_s) + 1)
    lam = np.zeros_like(t_axis, dtype=float)
    for t in entry_events:
        lam[min(int(t), len(lam) - 1)] += 1.0
    # smooth to per-minute rate (EMA of per-second counts, scaled by 60)
    ema = 0.0
    lam_per_min = []
    alpha = 0.18
    for v in lam:
        ema = (1 - alpha) * ema + alpha * v
        lam_per_min.append(ema * 60)

    # mu: service rate from mean dwell in service zone
    dwell = np.array(dwell_samples) if dwell_samples else np.array([1.0])
    mean_dwell = float(dwell.mean())
    p90_dwell = float(np.percentile(dwell, 90)) if len(dwell) else 0.0
    mu_per_min = 60.0 / mean_dwell if mean_dwell > 0 else 0.0

    # routing: normalize transition counts per row; remainder = exit
    P = np.zeros((len(room_names), len(room_names)))
    for i in range(len(room_names)):
        rowsum = transitions[i].sum()
        if rowsum > 0:
            P[i] = transitions[i] / rowsum * 0.92  # reserve ~8% exit mass

    out = {
        "clip_seconds": total_s,
        "entries": len(entry_events),
        "lambda_per_min_samples": [round(v, 4) for v in lam_per_min],
        "lambda_mean_per_min": float(np.mean(lam_per_min)) if lam_per_min else 0.0,
        "mu_per_min": float(mu_per_min),
        "mean_dwell_s": mean_dwell,
        "p90_dwell_s": p90_dwell,
        "dwell_samples": int(len(dwell)),
        "P": P.tolist(),
        "rooms": room_names,
        "transitions": transitions.tolist(),
    }
    Path(args.out).write_text(json.dumps(out, indent=2))
    print(f"estimate -> {args.out}")
    print(f"entries={len(entry_events)} lambda_mean/min={out['lambda_mean_per_min']:.2f} mean_dwell={mean_dwell:.1f}s mu/min={mu_per_min:.2f}")


if __name__ == "__main__":
    main()
