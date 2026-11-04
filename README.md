# CROWD GHOST

**Every crowd leaves a ghost. Fix it.**

A haunted-museum crowd simulation rendered as ASCII. Real queueing math under the hood — a Jackson network + Erlang C model, cross-checked against a social-force physics engine and a discrete-event simulation. You reshape the building; the **Curator** — a deterministic advisor with a terminal voice, *not* an LLM — tells you what the model predicts, and the split screen proves it.

The ghost is the crowd itself.

```
   .............................
   .                           .
   .                        @  .
   .                           .........................................................
   .                           .      @                    .                           .
   .                           .                           .                           .
   .    @  @    @         @ @ @.                           .                           .
   .    @     @   @ @ @ @@ @ @@.                           .                           .
   @ @  @  @    @    @   @@@ @@.@                          .                           .
  @. @   @  @ @   @  @@ @@ @@@@@ @ @                      @. @                         .
   .@@  @  @ @      @  @@ @@ @@. @                         .                           .
  @.     @  @  @  @  @   @ @@@@.                           .                           .
   .    @                 @   @.            @              .                           .
   .               @         @ .      @                    .                           .
   .                           .........................................................
   .                           .
   .............................
```
*Bottleneck, t = 25 s, seed 7 — lobby gridlocked, the hot exhibit unreachable, shop empty. This picture is the seed-7 physics run, not an illustration.*

## What's inside

- **Physics** — Helbing-style social-force engine (vectorised NumPy, spatial hash, capacity-enforced doors, door admission rate-limited by width × 1.3 persons/s). ~55–154 ticks/s sustained at 220–250 agents. Deterministic given a seed.
- **Math** — Jackson network with Erlang C per room (closed form), CTMC transient analysis, DES cross-checked against theory. Gate passed: theory inside DES CI.
- **The Curator** — rule templates fed by the *current* model solution. Every line carries a number that traces to the math. No free text generation → no hallucinated advice. `WHY?` prints the flow graph with per-room rho / offered load.
- **Split view** — A/B the current layout against the optimizer's candidate, same seed, same scenario, same sim time (B fast-forwards). Both panes render live.
- **Optimizer** — random search + DES ranking with a footfall floor (never wins by making the museum empty), physics-re-checked.
- **Stochastic truth** — the numbers you see live: departures-based utilization estimate ρ̂ (8 s EMA) for the gauge/stub, steady-state Erlang C for the Curator, Little's law for queued rooms' waits. Labeled, not blended into mush.
- **Ghost card** — one button exports a PNG poster of *this run* (ASCII frame + measured score + layout ID).

## Quickstart

Requirements: Python 3.11+, Node 20+ (frontend dev only).

```bash
# backend (serves API + built frontend at :8000)
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# open http://127.0.0.1:8000/
```

Keys: `1` GHOST (ASCII) · `2` X-RAY · `3` PLAN · `4` SPLIT · `5` CURATOR · `Esc` close overlay.

Environment: `CROWD_GHOST_LEVEL=bottleneck|lobby|rush|firedrill|realfootage` (default `lobby`).

### Docker

```bash
docker build -t crowd-ghost .
docker run --rm -p 8000:8000 crowd-ghost
# open http://127.0.0.1:8000/
```

The image builds the frontend (Node) and serves it from FastAPI (Python). No external services.

## The five halls

| Hall | Character |
|---|---|
| VERNISSAGE — FULL HOUSE (lobby) | Every room at rho ≈ 0.90; queues everywhere; finitely served |
| THE RUSH — OPENING NIGHT (rush) | 9 arrivals/s peak; the clean optimizer story (DES + physics both win) |
| THE BOTTLENECK (bottleneck) | One hot exhibit, 6 slots, 12 s dwell, λ = 4.5/s — 18× oversubscribed by design |
| FIRE DRILL (firedrill) | 180 pre-filled agents, gamma = 0, evacuation; scored on time-to-clear |
| REAL FOOTAGE — SYNTHETIC CLIP (realfootage) | Parameters from the offline vision estimate (see Limitations) |

## Stage gates — how this was built

One stage at a time; gate must pass before moving on. Full detail in `STAGE_*.md`.

| Stage | Gate result |
|---|---|
| 1 Skeleton | PASS — WS binary frames, Three.js dots, protocol codec |
| 2 Math core | **PASS** — theory vs DES inside CI (c=1 exact; c=2 lobby ~2.5% non-Poisson, documented) |
| 3 Physics | **PASS** — 0 wall tunnelling, 153 ticks/s at 250 agents, door-density ratio 495× |
| 4 Render + ASCII | PASS — render cost 0.88 ms/frame (~1100 fps headroom); host rAF throttling reported honestly |
| 5 Vision (offline) | PASS — synthetic clip, blob detector, **entry error 1.6%** (gate ≤ 15%) |
| 6 Optimizer | PASS, partial — rush wins DES+physics; bottleneck DES 6.53→0.00 s (physics samples tiny, reported); lobby physics tie (reported) |
| 7 UX + Curator | PASS — every Curator claim numbered & model-traced; split view A/B same seed |
| 8 Levels + launch | This note |

## Honest numbers

Fresh seed-7 straight runs (`tools/score.py`, mean wait & crush **measured**, not modeled; rooms-seen from the Markov routing, labeled):

| Level | Mean wait/exit | Crush idx | Score | Notes |
|---|---|---|---|---|
| lobby | 0.00 s | 0.0% | **100** | Full house, no standing queue |
| rush | 1.51 s | 0.0% | **94** | Peak-hour pressure, holding |
| bottleneck | **30.73 s** | 0.0% | **0** | Gridlocked by design |
| realfootage | **63.85 s** | 0.0% | **0** | Clip-measured λ hammers the 6-slot hot exhibit |
| firedrill | time-to-clear **16.7 s** (181/181 exits) | 0.0% | — | Evacuation metric, no queueing score |

Optimizer (Stage 6, DES-ranked): bottleneck **6.526→0.000 s** wait (+100%); rush **0.062→0.005 s** (+91.6%) and physics peak queue 12→7; lobby DES win / physics tie (both 0.00 — nothing to fix in 50 s of sim; reported as-is).

Theory vs sim: `results/theory_vs_sim.png` (regenerate with `tools/validate_theory_vs_sim.py`).

## Honest limitations — read these before trusting a number

1. **The vision gate used a synthetic clip.** The clip was rendered from this very simulator; the estimator's 1.6% entry error is against *simulation ground truth*, not reality. No licensed crowd footage was obtainable or redistributed; `data/clips/LICENSES.md` records this. YOLOv8n detected **0** persons on rendered dots (expected). **A real-footage hand-count validation never happened.** Don't quote the vision number as field performance.
2. **Bottleneck is infeasible on purpose.** There is no steady state — λ/(c·μ) = 9.0 at the hot exhibit. The sim survives via door admission throttling + hard capacity; the analytical model (correctly) refuses to produce a steady-state rho and the Curator says exactly that.
3. **Two rhos, both honest.** The HUD gauge/stub show live ρ̂ (departures/EMA utilization, warms in ~8 s, converges from below); the Curator shows steady-state Erlang C (or offered load when infeasible). They disagree in transient moments by construction.
4. **Split side B is the optimizer's candidate, not a guarantee** (Stage 6 caveats apply; physics samples at bottleneck are tiny — DES is the reliable signal there).
5. **lobby physics tie** and **bottleneck DES-only signal** are reported failures of measurement, not hidden.
6. **No sound, no asciinema clip, no demo GIF, no public URL in this repo.** The 10 s loop / 30–60 s video / hosting are owner deliverables, not claims. Cold-start behaviour is documented from local Docker below (public-URL gate **not verifiable from here — NOT VERIFIED**).
7. **Scoring weights are a design choice** (12 pts/s wait, 150 pts crush fraction, +4/room seen). They rank this museum; don't use them to rank anything else.
8. **`npm run build` must pass cleanly.** A `tsc` error once shipped a stale bundle; the build now fails loudly instead (and this README's tables come from fresh runs).

## Reproduce everything

```bash
python -m pytest tests -q                      # 27 tests
python tools/bench_physics.py bottleneck       # physics gate: ~72 ticks/s
python tools/validate_theory_vs_sim.py         # DES vs theory plot
python tools/validate_vision.py                # vision estimator vs sim ground truth
python tools/optimize_layout.py                # re-derive results/optimizer.json (~3.5 min)
python tools/score.py                          # re-derive results/scores.json
```

## Deploy notes (cold start)

Docker image: 327 MB (`python:3.11-slim` runtime after a `node:20` build stage; runtime deps only: fastapi/uvicorn/numpy). Single process, no DB, no queues — uvicorn serves HTTP + WebSocket (binary frames, 30 Hz). **Cold start, measured from `docker run` to first `/api/health` 200: ~1.6–2.3 s** (build machine dependent); static bundle ~535 kB (gzip ~139 kB), fonts self-hosted. No GPU required; the constraint is the client's WebGL, not the server. Set `CROWD_GHOST_LEVEL` to choose the opening hall. One authoritative sim is shared by all connected clients — physics steps once per tick regardless of client count, by design.

**Cold start check that was actually run** (not just documented): `docker build -t crowd-ghost .` → `docker run -d -p 8001:8000 crowd-ghost` → poll `/api/health` → 200 OK in ~1.6–2.3 s. A **public URL was never created from this environment** — the plan's "public URL loads first 3 levels in under 5 s" gate is therefore **NOT VERIFIED** here (it needs a hosting choice); deploying the image to any container host gives the same cold start.

## Layout

```
backend/app/physics/    social-force engine (deterministic, seed-bound)
backend/app/model/      Jackson network, Erlang C, CTMC, DES
backend/app/optimize/   objective + DES-ranked random search
backend/app/curator/    deterministic advisor + WHY? graph
backend/app/scoring.py  score = f(mean wait, rooms seen, crush index)
frontend/src/           Three.js panes, tactical-telemetry UI, ghost-card export
results/                optimizer.json, theory_vs_sim.*, scores.json (scores.local)
STAGE_*.md              per-stage build notes with gate numbers
```
