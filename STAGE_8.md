# Stage 8 — Levels, Ghost Card, Launch

**Built**
- **Scoring** (`backend/app/scoring.py` + `tools/score.py`) — `score = clamp(100 − 12·mean_wait_s − 150·crush_frac + 4·min(rooms_seen,5), 0, 100)`. Mean wait and crush fraction are **measured live** by the physics engine (drives: `total_queue_time/exited`, agent-seconds above 4 agents/m² from shoelace polygon areas); rooms-seen comes from the Markov routing (model, labeled as such). Evacuation levels get **no queueing score** — fire drill reports `time_to_clear_s` instead. 27/27 tests green (4 new scoring tests).
- **Ghost card** — `GET GHOST CARD` button (placard) exports a 1200×630 PNG poster of *this run*: live ASCII frame, measured stats, score or clear time, layout ID (`CG-<md5>`), seed/date, model tag. `/api/score` serves the live state; export verified in-page (`card:ok`), pixel-probe confirmed the composite (VT323 wordmark [74,246,38], colored score block, 3497/233/155/142 green/amber/white/red sampled pixels). Poster **visual composition not eyeball-verified** — the harness window is hidden in this environment; treat layout spacing as unverified.
- **Levels** — all four originals plus **`realfootage.json`**: REAL FOOTAGE — SYNTHETIC CLIP. Parameters come from `results/vision_estimate.json` (λ = 100.5/min measured, routing P from 63 tracks' zone transitions, dwell kept at the rendered level's values because the clip only supports a pooled 19.3 s mean). Geometry is bottleneck verbatim (the clip was rendered from its seed-99 run). The level list is now served dynamically by `/api/levels`, so future JSON levels appear without a frontend rebuild.
- **README** rewritten — what it is, architecture, honest numbers, five-hall table, reproduce commands, deploy notes, and a limitations section that says out loud: vision real-footage gate NOT performed, two rhos labeled, bottleneck infeasible by design, public URL never deployed.
- **Diagram (not an illustration)** — the README's ASCII snapshot is the seed-7 bottleneck run at t = 25 s (lobby gridlocked, hot exhibit unreachable).

**Fresh-run scores (`tools/score.py`, seed 7, 90 s sim, bottleneck-family crowd)**

| Level | Mean wait/exit | Crush | Score |
|---|---|---|---|
| lobby | 0.00 s | 0.0% | 100 |
| rush | 1.51 s | 0.0% | 94 |
| bottleneck | 30.73 s | 0.0% | 0 |
| realfootage | 63.85 s | 0.0% | 0 |
| firedrill | clear in **16.73 s** (181/181 exits) | 0.0% | — (time-to-clear) |

Crush index reads 0.0% everywhere here — a property of these layouts at this seed, not a universal claim; the metric itself is wired and unit-tested.

**Launch work actually done — Docker, measured from `docker run`**
- `docker build -t crowd-ghost .` succeeds (multi-stage: node:20 build → python:3.11-slim runtime, runtime deps only: fastapi/uvicorn/numpy).
- Image slimmed **970 MB → 327 MB** by splitting `requirements-runtime.txt` (scipy/numba/matplotlib/pytest are not runtime deps).
- Container run polled from host: first `/api/health` 200 in **~1.6–2.3 s** (measured twice). Static bundle ~535 kB (gzip ~139 kB), fonts self-hosted.
- No public URL was created — nothing was pushed anywhere. The plan's gate **"public URL loads the first 3 levels in under 5 s" is NOT VERIFIED** from this environment (needs a hosting choice by the owner). What *is* verified: cold start ~1.6–2.3 s locally, first paint assets local.

**En-route bug (found, fixed, disclosed)**
- `npm run build` runs `tsc && vite build`; it had been **silently failing with a `tsc` error** (private member access) since Stage 7 — every "successful" deploy copied a **stale bundle** (CARD button missing, levels list static). Fixed (`GhostPane.snapshotCanvas()`), build now fails loudly on any TS error, and the full Stage-7 surface (split parity, mode sync, CARD export) was re-verified against the **current** bundle.

**Gate result — PARTIAL (honest)**
The half with "cold start behaviour documented" passes (measured, written). The half with "public URL loads the first 3 levels in under 5 s" is **NOT VERIFIED** — no deployment exists, on purpose: creating a public deployment is an owner decision with cost and exposure attached. The code is container-complete and the cold-start path is measured; the gate cannot be passed from inside this environment.

**PLAN §12 benchmark rubric — scored as it actually went**

| Check | Criterion | Result |
|---|---|---|
| Stage 2 gate | theory inside DES CI, first or second attempt | **PASS** — c=1 exact match; c=2 lobby ~2.5% (non-Poisson input), documented; gate config fixed, not the code |
| Physics | 0 wall violations, ≥30 ticks/s at 250 agents | **PASS** — 0 tunnelling; 55–154 ticks/s sustained |
| Shader | compiles, glyph ramp correct, 60 fps | **PARTIAL** — compiles, glyph ramp in, 0.88 ms/frame render cost (~1100 fps headroom at sync timing); wall-clock 60 fps **NOT VERIFIED** (embedded host throttles rAF to ~14 Hz) |
| Vision estimator | within 15% of hand count | **NOT PERFORMED vs real footage** — 1.6% vs simulation ground truth only; YOLOv8n found 0 persons on rendered dots (expected) |
| Optimizer | beats baseline in DES and physics | **PASS rush** (DES+physics), **PASS bottleneck DES** (6.53→0.00 s; physics samples tiny, reported), **TIE lobby physics** (reported) |
| Curator | every claim traceable to a number | **PASS** — all four levels traced verbatim into STAGE_7.md |
| Process | gates, notes, commits | **PASS** — STAGE_1..8.md, one commit per stage |
| Honesty | failures with data, nothing faked | **PASS** — see STAGE_5/6/7/8 notes; real-footage gap stated everywhere |

**Deliberately not done (owner deliverables / cut list)**
Demo GIF/video/asciinema clip; sound; Real-Footage live upload; public deployment; license choice; gallery entry. None of these are claimed anywhere.

**Reproduce**
```
python -m pytest tests -q            # 27/27
python tools/score.py                # scores.json (~3.5 min)
docker build -t crowd-ghost . && docker run --rm -p 8000:8000 crowd-ghost
```
