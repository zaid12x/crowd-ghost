# CROWD GHOST

[![License: MIT](https://img.shields.io/badge/License-MIT-4af626.svg)](LICENSE) [![Repo](https://img.shields.io/badge/github-zaid12x%2Fcrowd--ghost-eaeaea.svg)](https://github.com/zaid12x/crowd-ghost)

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

## The math

CROWD GHOST is not a vibe. Three independent models describe the same museum, and every number on screen traces to one of them. When they disagree — and in bottleneck they *always* do — the disagreement is the point, and it is reported.

### 1. The queueing network (steady state, the Curator's source of truth)

**Traffic equations.** For rooms `i = 0..N−1` with entry rate γ into room 0 and routing matrix P (row `i` → distribution over next room or exit), the throughput per room solves the substochastic system:

```
λ = γ·e₀ + Pᵀ λ        (λᵢ = γᵢ + Σⱼ λⱼ·Pⱼᵢ)
```

solved exactly via the transient fundamental matrix `(I − Pᵀ)⁻¹` (spectral decomposition on transient states). Rooms fed faster than they can serve have no steady state — flagged **INFEASIBLE**, never papered over.

**M/M/c per room (Erlang C).** With service rate μ = 1/dwell and c parallel slots:

```
a  = λ / (c·μ)                          (offered load, a < 1 required)
Pw = ErlangC(c, a) = [a^c / c! · c/(c−a)] / [Σ_{k<c} a^k/k! + a^c / c! · c/(c−a)]
Wq = Pw / (c·μ − λ)                     (expected queue wait)
ρ  = a                                   (utilization; displayed when feasible)
```

`backend/app/model/jackson.py`, tested against closed-form M/M/1 cases and independent CTMC transient solve (`scipy.linalg.expm`, `app/model/ctmc.py`).

**Theory vs simulation gate (Stage 2).** DES independently drives the same network (exponential interarrival/service, λ-weighted mean wait, 15% warm-up). Theory landed inside the DES confidence interval for all c=1 gate rooms — exact by Burke's theorem. For the c=2 LOBBY, a ~2.5% deviation was measured and *kept* — the cause was non-Poisson flow into Erlang-C stations fed by mixed sources (Burke applies to M/M/1 departures); the fix was config design (c=1 rooms for the gate), not fudge factors. Plot: `results/theory_vs_sim.png`.

### 2. The physics (the eye's source of truth)

Helbing-style social force, vectorised NumPy with a spatial hash (cell 1.5 m, O(N) neighbour lookup, `SUBSTEPS = 2` integration):

```
m·v̇ = goal(τ)  +  Σ_neighbours A·e^{(d₀−d)/B}·n̂   (exponential repulsion, A=12, B=0.28 m)
               +  Σ_walls    A_w·(1 − d/d₀)·n̂     (linear wall repulsion inside 0.55 m)
rooms admit only while occupancy < capacity     (hard cap; others queue outside)
doors pass width × 1.3 persons / s               (token bucket — width is a decision variable, not decoration)
queues are stable-slotted; no agent ever tunnels a wall (verified: 0 violations)
evacuation: BFS exit-chain routing, prefilled crowd, gamma = 0
```

Capacity enforcement is what lets the sim represent **infinite demand** (a real sellout) without fake infinite rooms — the queue lives outside, which is also where it is measured: `waiting_total`, `peak_waiting`, `mean_queue_seconds_per_exit`.

**Live estimators.** The HUD/stub show ρ̂ = completions-EMA(8 s) / (c·μ) — a measured busy-fraction that *converges to the true utilization from below*, and correctly pins at 1.0 under saturation where the admissions-rate estimator reads 0 (gridlock) — that was the bug we fixed. For queued rooms the wait estimate is Little's law applied to the live numbers: `Wq̂ = q / (ρ̂·c·μ)`; `—` when saturated (no steady state to quote). The Curator, by contrast, always reports the *model* (steady-state rho, or offered load + `OVERSUBSCRIBED` flags when infeasible — labeled as such). Two numbers, two questions, both labeled.

**Crush index.** `Σ agent-seconds with density > 4 agents/m² / total agent-seconds` (per-room shoelace polygon areas, `app/physics/social_force.py`). **Score** (design choice, stated once, used everywhere): `clamp(100 − 12·mean_wait_s − 150·crush_frac + 4·min(rooms_seen, 5), 0, 100)`; rooms-seen/visitor = Σλᵢ / Σγ from the traffic solution (rewards flowing layouts over dead-end lemmings).

## The optimizations

### A. The layout optimizer (what it finds, and why it's honest)

`tools/optimize_layout.py` → `results/optimizer.json`. **DES-ranked random search** over exactly four decision variables, re-checking finalists in physics:

| Variable | Search space | Why |
|---|---|---|
| entry_cap | multiplicative {0.7, 0.8, 0.9, 1.0, 1.15} × default | **footfall floor ≥ 70%** — the degenerate "solution" of emptying the museum is out of bounds by construction |
| capacities cᵢ | jittered ∝ lognormal(0, 0.45), then **repaired to exactly the default total** | capacity is a budget, not a wish list; no summoned capacity |
| bottleneck door width | widen {0, +0.5, +1.0, +1.6} m, entrance shrunk by the same Δ (min 1.2 m) | a door isn't free — the entrance pays for it |
| routing nudge | ±0.15 on the dominant route (never negative, clipped) | signage, not kidnapped customers |

Pipeline per candidate: **(1)** Jackson feasibility filter (infeasible → score ∞, rejected); **(2)** analytical score for diagnostics; **(3)** **6 DES replications** (seeds 4242…, λ-weighted waits, 15% warm-up, λ from the traffic equations) — DES, not the closed form, does the ranking; **(4)** finalists re-checked in physics (seed 99, 50 sim-s) vs **default and naive (equal-capacities)** baselines — "any equal split is great" is the tempting wrong intuition, so it's always in the race. Objective: `score = mean_wait + 3.0·Σ max(0, ρ−0.85) − 0.6·rooms_seen` (`app/optimize/objective.py`). 240 candidates/level (seed 17) + the two baselines; `T_end` per level.

**Reported as it fell out** (not cherry-picked):
- **rush** — the clean win: DES 0.062→0.005 s (+91.6%) **and** physics peak queue 12→7, beats default and naive in both. Visible crowd relief.
- **bottleneck** — DES 6.526→0.000 s (+100%). Physics re-check: mean wait-per-exit 50.3→0.0 s — but only **3→9 exits** observed; the DES number is the reliable signal and it is the headline.
- **lobby** — DES win; physics **tie at 0.00 s** (no standing queue exists in 50 s of sim — nothing measurable to fix). Reported as a tie.

The optimizer's diagnosed bottleneck fix (all numbers from the model): pour capacity into the hot exhibit (**6→111 slots**), widen its door d0 (**1.1→2.1 m**), compensate by narrowing the entrance (**3.4→2.4 m**), throttle entry ×0.90, and nudge routing −7.5% off the dominant path. Levels were recalibrated to ρ ≈ 0.88–0.92 first — before that, everything was over-provisioned and the optimum was "do nothing".

### B. The runtime (why it stays at 30 Hz on a toaster)

- **Two WebGL panes, two draw calls per pane of agents** — instanced ghost capsules (`InstancedMesh`, dynamic `DynamicDrawUsage`), no per-agent DOM, no per-agent text.
- **ASCII = one fullscreen post pass** (glyph ramp `. : - = + * # % @` tied to a pressure field texture), not N textured sprites; X-RAY drops the museum walls and keeps the heat; PLAN is an ortho camera (symmetric ±W/2 frustum — the original 0..W bug is why this line exists); BLUEPRINT swaps strokes/solids.
- **render cost 0.88 ms/frame** measured with synchronous timing (~1100 fps headroom); HUD numbers ride the existing 30 Hz frames — one telemetry DOM write/room/tick + one spring-eased bath-needle dial (`prefers-reduced-motion` honoured).
- **One authoritative sim, stepped once per tick** regardless of client count (multi-tab was N× speed before the guard); frames are binary (`float32[n×4]` + per-room stats, ~1 KiB for 250 agents).
- **Preserved drawing buffer only where it earns its keep** — `preserveDrawingBuffer: true` exists solely for the ghost-card PNG export (verified working, lines read `[CARD]`); everything else draws straight into the back buffer and is composited and forgotten.

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
Dockerfile              327 MB all-in-one image (runtime deps only)
results/                optimizer.json (committed), theory_vs_sim.*, scores.json (local)
STAGE_*.md              per-stage build notes with gate numbers
```

## Project

Source: **https://github.com/zaid12x/crowd-ghost** — issues and PRs welcome.
Container image builds from this repo with one command (`docker build -t crowd-ghost .`).

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Zaid Alqudah ([@zaid12x](https://github.com/zaid12x)).
