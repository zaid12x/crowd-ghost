# Stage 7 — UX + Curator

**Built**
- **Split view** — two panes side by side (A = current layout, B = optimizer candidate layout from `results/optimizer.json` for the level, same seed 7). `set_split` rebuilds engine B, which **fast-forwards to engine A's elapsed sim time** (budget-capped at 240 physics steps per tick, so no frame stalls and both panes are comparable immediately). B falls back to the level's current parameters if the optimizer artifact is missing/absent. Frames carry `FLAG_SIDE_B` (0x02); the client routes them to pane B. `4 SPLIT` toggles; both panes always render the same visual mode; captions `[ CURRENT LAYOUT ]` / `[ OPTIMIZED ]`; ticket stub reads `AGENTS 220 ⇄ 202` plus an **OPTIMIZED (B)** aggregate row (agents, worst rho, queued).
- **SERVICE PANEL** (right rail) — HALL/LEVEL select (four levels), entry-rate slider (`gamma_scale` 0.2–1.5), per-room capacity sliders, door-width sliders. Changes hot-reload the sim over WS (`{type:'params'}`), no reset; left pane only by design (noted in the panel footer). RESET restores server defaults.
- **TICKET STUB** (left rail) — per-room rows: rho (8-cell load bar), Wq, queue; OVERLOAD hazard banner fires at rho > 0.85 (`LOBBY RHO 1.00 — QUEUE SELF-FEEDING` style, deterministic text).
- **CROWD PRESSURE galvanometer** (left rail) — anatomy-style analog dial; needle = max room rho, spring-eased (k=90, c=14), red zone ≥ 0.85; `prefers-reduced-motion` snaps instantly.
- **Curator** (deterministic) — Jackson network + Erlang C **re-solved at request time** for the current layout (gamma/capacities from live server state). No LLM anywhere: every line is a template filled with a model number. `WHY?` overlay renders the ASCII room graph — feasible levels show per-room rho/Wq + flow arrows; infeasible levels (bottleneck) show **offered load a = lambda / (cap·mu)** with an `<< OVERSUBSCRIBED` flag instead of a fake rho. Entry-throttle advice re-solves Erlang C at 0.8× entry rather than scaling linearly. Capacity fix picks the *cheapest* factor (1.5×/2×) achieving ~the best predicted Wq delta (no pointless 3× prescription).
- **Design system** — tactical-telemetry / CRT (industrial-brutalist-ui §2.2): `#0A0A0A` substrate, IBM Plex Mono + VT323 self-hosted via Fontsource (no CDN), phosphor green `#4AF626`, hazard red `#E61919` (overload only), amber `#ffb000`, zero radius, scanline + grain overlays (fixed, inert), CSS-grid 3-column cockpit with ≤840 px stacked fallback. Anatomy built one living instrument on the HUD: the pressure dial.

**Live-metric fixes made this stage (each found in the running app, each fixed, each verified)**
- **Wire rho was an admissions-rate EMA** — it decayed to 0 exactly under gridlock, the one moment it mattered. Replaced with a **departures-based utilization estimate** ρ̂ = completions_EMA / (capacity · mu) (8 s EMA): pins near 1.0 under saturation, and discriminates a healthy-but-full room (lobby ≈ 0.1) from a meltdown (hot exhibit ≈ 0.5–1.0).
- **Wq showed 0.0 s while a queue existed** — now Little's law on the live estimator (`queue / departure_rate`) when a queue is non-empty; `—` at saturation (no steady state to quote).
- **Side B started from t=0** while A had been running for minutes — lopsided A/B. B now catch-up fast-forwards to A's elapsed time (above).
- **N browser tabs = N× physics speed** — the shared sim advanced once per connection. Physics now advances at most once per DT per server regardless of client count.
- **Browser form-state restore silently overrode parameters on reload** — observed door widths pushed 3.4→2.8 on every boot; mode flipped to PLAN via a replayed `3` keydown. Param and keydown echoes are now dropped for 2.5 s after boot.
- **Curator "RHO=9.00" honesty check** — verified the underlying claim: bottleneck hot exhibit has λ=4.5/s vs capacity·mu = 6 × (1/12 s) = 0.5/s, so the offered load genuinely is a = 9.0 and no steady state exists. The alert text says so; the number traces; it is not dressed up as a steady-state rho.

**Gate result — PASS**

Every Curator claim includes a number that traces to the model — printed verbatim per level, zero prose invention:

```
lobby      [alert] GALLERY A AT RHO 0.90 (>0.85). NO WAIT YET (0.7s) BUT ZERO HEADROOM.
           [warn ] FIX: GALLERY A CAPACITY 50 -> 75 (+25). MODEL PREDICTS WAIT 0.7s -> 0.0s (-0.7s).
           [warn ] ENTRY AT 5.00/s. THROTTLING TO 4.00/s PREDICTS WORST RHO 0.72 (ERLANG C, RE-SOLVED).
           [ok   ] ROOMS SEEN PER VISITOR: 3.00.
bottleneck [alert] HOT EXHIBIT IS OVER CAPACITY. RHO=9.00 -- QUEUE GROWS WITHOUT BOUND.
           WHY?   [HOT EXHIBIT]  a=9.00  cap=6  << OVERSUBSCRIBED
firedrill  [ok   ] FLOW IS NOMINAL. ZERO ENTRY FLOW -- NOTHING TO QUEUE.
```

**Live check (this session, fresh boot, bottleneck)**
- `/api/health`: agents 220, `split=true`, `side_b_agents=202`, door widths at file defaults (echo guard holding), 23/23 tests green, frontend builds clean, zero console errors.
- A pane: LOBBY rho 0.02 / HOT EXHIBIT rho 0.50, queue 02, Wq 8.0 s (Little's law distilled from the live estimator) / SHOP 0.01.
- B pane (optimized): worst rho 0.28, queued 0 — visible, honest divergence. The optimizer's candidate (hot exhibit 6→111 caps, entry ×0.90) is genuinely uncongested at this load; its cost is ~10% throttled entry, visible in the ticket stub counts.

**Honest caveats**
- Live ρ̂ is a warming 8 s estimate, not the exact steady-state rho. Under saturation it converges from below (seen 0.5–1.0 depending on churn). Steady-state numbers live in the Curator; gauge/stub use ρ̂. Different quantities, labeled as such.
- Bottleneck is *designed* to be infeasible at the door (18× oversubscribed); the sim survives via door admission throttling + capacity-enforced occupancy, not because the model is feasible. The Curator's job here is to say exactly that.
- Split B is the optimizer's *candidate*, not a guarantee; Stage 6 caveats carry over (rush is the clean physics win; bottleneck DES-only meaningful).
- The split toggle rebuilds B and fast-forwards; on a multi-hour session the catch-up cap keeps the cost bounded but the first seconds after toggle are approximate on very long runs.
- Entry-spacing slider (plan §Stage 7) folded into ENTRY RATE (gamma); no separate control.
- HUD FPS is the embedded browser's throttled rAF (~14–60), not app cost; render path measured 0.88 ms/frame (Stage 4).
- The embedded browser replays stale input on reload; mitigated (2.5 s echo guard), not eliminated. Do not treat boot-state quirks as app bugs without checking server health first.

**Reproduce**
```
cd backend
CROWD_GHOST_LEVEL=bottleneck python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# open http://127.0.0.1:8000/ → 4 SPLIT (A/B, same seed) · 5 CURATOR + WHY? · 1/2/3 modes · sliders hot-reload
python -m pytest tests -q
```
