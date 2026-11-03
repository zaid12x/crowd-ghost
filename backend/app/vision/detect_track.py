"""Offline detector/tracker: clip -> tracks.json.

Two detectors:
  --detector blob  (default) bright-blob threshold + connected components + greedy NN tracking.
                   Robust on rendered synthetic clips (dark scene, bright people).
  --detector yolo  YOLOv8n + built-in ByteTrack via ultralytics (if installed). Unusable on
                   synthetic dots (they are not persons); kept for real footage.

Output: tracks.json with per-track positions (centroids) per frame.
"""
import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np


def detect_blob(frame, thresh):
    """Bright-blob person detector with overlap separation.

    Threshold -> distance transform -> local-maximum peaks (each peak is one
    person, even inside a merged blob). Falls back to centroid of components
    when no peaks are found in a component.
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    _, bw = cv2.threshold(gray, thresh, 255, cv2.THRESH_BINARY)
    bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    dist = cv2.distanceTransform(bw, cv2.DIST_L2, 5)
    kernel = np.ones((5, 5), np.uint8)
    dilated = cv2.dilate(dist, kernel)
    peaks = ((dist == dilated) & (dist > 2.3)).astype(np.uint8)
    n, _, stats, cents = cv2.connectedComponentsWithStats(peaks, connectivity=8)
    dets = []
    used = np.zeros_like(bw, dtype=bool)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= 1:
            dets.append((float(cents[i][0]), float(cents[i][1])))
    return dets


def detect_yolo(model, frame, conf):
    results = model.track(frame, persist=True, conf=conf, verbose=False)[0]
    dets = []
    if results.boxes is None:
        return dets
    for box in results.boxes:
        cls = int(box.cls[0]) if box.cls is not None else -1
        if cls != 0:  # person
            continue
        x, y, w, h = box.xywh[0].tolist()
        dets.append((float(x), float(y)))
    return dets


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clip", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--detector", choices=["blob", "yolo"], default="blob")
    ap.add_argument("--thresh", type=int, default=150)
    ap.add_argument("--max-step", type=float, default=22.0)
    ap.add_argument("--max-missing", type=float, default=1.5)
    args = ap.parse_args()

    cap = cv2.VideoCapture(args.clip)
    fps = cap.get(cv2.CAP_PROP_FPS) or 12.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    model = None
    if args.detector == "yolo":
        from ultralytics import YOLO
        model = YOLO("yolov8n.pt")

    tracks = {}       # id -> {"points": [(f, t, x, y)], "missing": float}
    active = {}       # id -> (x, y)
    next_id = 1
    fi = 0
    log = []

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if args.detector == "blob":
            dets = detect_blob(frame, args.thresh)
        else:
            dets = detect_yolo(model, frame, 0.25)

        # greedy nearest-neighbor assignment
        unmatched = list(dets)
        assigned = set()
        for tid, (tx, ty) in list(active.items()):
            best_d, best_j = args.max_step, None
            for j, (dx, dy) in enumerate(unmatched):
                if j in assigned:
                    continue
                d = math.hypot(dx - tx, dy - ty)
                if d < best_d:
                    best_d, best_j = d, j
            if best_j is not None:
                dx, dy = unmatched[best_j]
                assigned.add(best_j)
                tracks[tid]["points"].append((fi, round(fi / fps, 3), dx, dy))
                tracks[tid]["missing"] = 0.0
                active[tid] = (dx, dy)
            else:
                tracks[tid]["missing"] += 1.0 / fps
                if tracks[tid]["missing"] > args.max_missing:
                    del active[tid]
        for j, (dx, dy) in enumerate(unmatched):
            if j in assigned:
                continue
            tracks[next_id] = {"points": [(fi, round(fi / fps, 3), dx, dy)], "missing": 0.0}
            active[next_id] = (dx, dy)
            next_id += 1
        fi += 1

    cap.release()

    # drop noise-born fragments: a real pedestrian track persists >= 5 frames
    kept = {tid: tr for tid, tr in tracks.items() if len(tr["points"]) >= 5}

    out = {
        "clip": args.clip,
        "fps": fps,
        "width": width,
        "height": height,
        "detector": args.detector,
        "track_count": len(kept),
        "tracks": [{"id": tid, "points": v["points"]} for tid, v in sorted(kept.items())],
    }
    Path(args.out).write_text(json.dumps(out))
    print(f"tracks -> {args.out}")
    print(f"tracks={len(tracks)} frames={fi} detector={args.detector}")


if __name__ == "__main__":
    main()
