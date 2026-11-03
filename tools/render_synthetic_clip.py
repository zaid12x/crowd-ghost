"""Render the physics sim top-down to an mp4 for the vision pipeline.

Dark scene, bright compact blobs (people), no walls — the blob detector must
find movers. Emits the clip and a ground-truth JSON (spawn times, per-room
admission times) for gate validation.
"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.physics.social_force import PhysicsEngine, DT

W, H = 960, 540
WORLD_W, WORLD_H = 46.0, 30.0
SCALE = H / WORLD_H
OFFSET_X = (W - WORLD_W * SCALE) / 2


def to_px(x, y):
    return int(OFFSET_X + x * SCALE), int(y * SCALE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", default="bottleneck")
    ap.add_argument("--seconds", type=float, default=90.0)
    ap.add_argument("--fps", type=int, default=12)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--max-agents", type=int, default=140)
    ap.add_argument("--out", default="data/clips/synthetic.mp4")
    ap.add_argument("--truth", default="data/clips/synthetic_truth.json")
    args = ap.parse_args()

    with open(Path("backend/data/levels") / f"{args.level}.json", "r", encoding="utf-8") as f:
        level = json.load(f)

    eng = PhysicsEngine(level, seed=args.seed, max_agents=args.max_agents)
    root = Path(__file__).resolve().parent.parent
    clip_path = root / args.out
    truth_path = root / args.truth
    clip_path.parent.mkdir(parents=True, exist_ok=True)

    writer = cv2.VideoWriter(str(clip_path), cv2.VideoWriter_fourcc(*"mp4v"), args.fps, (W, H))
    events = []          # (time, agent_id) spawn/entry events
    seen_ids = set()

    frames = int(args.seconds * args.fps)
    sub = max(1, round((1 / args.fps) / DT))
    rng = np.random.default_rng(42)

    for fi in range(frames):
        for _ in range(sub):
            eng.step(DT)
        t = eng.time
        # log entries (agents we haven't logged yet)
        for a in eng.agents:
            if a.id not in seen_ids:
                seen_ids.add(a.id)
                events.append({"id": a.id, "t": round(t, 3)})
        # draw
        frame = np.zeros((H, W, 3), dtype=np.uint8)
        frame[:] = (12, 14, 12)
        # faint floor plan for realism (not person-shaped)
        for room in level["rooms"]:
            pts = np.array([[to_px(p[0], p[1]) for p in room["polygon"]]], dtype=np.int32)
            cv2.polylines(frame, pts, True, (26, 30, 26), 1)
        # people: bright filled circles with slight radial falloff
        for a in eng.agents:
            x, y = to_px(a.x, a.y)
            cv2.circle(frame, (x, y), 7, (200, 205, 190), -1, cv2.LINE_AA)
            cv2.circle(frame, (x, y), 4, (235, 238, 224), -1, cv2.LINE_AA)
        # subtle noise grain
        noise = rng.integers(0, 14, frame.shape, dtype=np.int16)
        frame = np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        writer.write(frame)

    writer.release()

    truth = {
        "level": args.level,
        "seed": args.seed,
        "seconds": args.seconds,
        "fps": args.fps,
        "entries": events,
        "entry_count": len(events),
        "agents_final": len(eng.agents),
        "gamma_truth_per_s": level["gamma"],
        "world_scale_offset": [OFFSET_X, 0.0],
        "scale": SCALE,
    }
    truth_path.write_text(json.dumps(truth, indent=2))
    print(f"clip -> {clip_path}")
    print(f"truth -> {truth_path}  entries(spawns)={len(events)}")


if __name__ == "__main__":
    main()
