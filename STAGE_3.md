# Stage 3 — Physics

**Built**
- `backend/app/physics/floorplan.py` — rooms (polygons), doors (capacity gaps). Walls auto-derived: room edges minus door gaps, plus a **closed perimeter** (bounds rectangle) so the site is fully enclosed. Vectorized point→segment distance for wall forces.
- `backend/app/physics/social_force.py` — Helbing social-force engine: goal force (τ=0.5 s, desired speed 1.3–1.6 m/s), agent-agent exponential repulsion (spatial hash), wall repulsion + hard de-penetration (no tunneling), semi-implicit Euler, 2 substeps per 30 Hz tick.
  - Room/door state machine: entrance admission → dwell → route via P → capacity check at doors → if full, agent **queues outside** (deterministic slots, lateral spread by agent id).
  - **BFS exit-chain routing** for evacuation (agents route through connected rooms to an actual exit instead of walking straight through walls).
  - EMA admission-rate per room + Erlang-C-derived Wq estimate streamed to the client (drives the Curator later).
  - Prefill support for Fire Drill (crowd starts inside).
- Levels: `lobby`, `rush` (opening night, ~250 agents), `bottleneck` (one hot exhibit, capacity 6, 1.1 m doors), `firedrill` (181 prefilled agents, 3 exits, evacuation routing).
- `tools/bench_physics.py` — headless 60 simulated-second gate bench + door-density probe.
- Frontend: fetches `/api/health` for level name + world bounds; server hot-reloads level via `{type:"level", id}` WS message.

**Gate result — PASS**
- Sustained 60 simulated seconds at 250 agents: **`rush` 65 ticks/s, `bottleneck` 153 ticks/s** (gate: ≥30 ticks/s). `rush` peaks at 249 agents.
- **0 wall-tunnelling violations** (agents clear of every wall after de-penetration; rooms + gaps + perimeter form the valid space).
- Spatial hashing in place; agent-agent cost is ~O(n × neighbours), wall forces vectorized per wall.
- Capacity enforced: hot exhibit occupancy never exceeds 6 (test); narrow door visibly queues — **peak waiting 14**, door-region density **2.1 agents/m² vs 0.009 in shop (238×)**.
- Fire Drill: full clear of 181 evacuees in ~17 simulated seconds, stable across seeds 7/11/23.
- Tests: 23 passing.

**Bugs fixed along the way (honest log)**
1. DES infinite-horizon bug (`while heap:` never terminated) — arrivals now bounded by `t_end`.
2. Spawned agents kept the entrance door as their target and walked backwards outside; admission now happens **at spawn** (agents enter the entrance room immediately).
3. Without a perimeter wall, agents pushed out the entrance drifted into the open bounds clip — fixed with a closed perimeter; `mask_inside` = inside site ∧ clear of walls.
4. Fire Drill agents beelined straight through solid walls toward "nearest exit" — fixed with BFS exit-chain routing and capacity-free movement during evacuation; exit admission radius relaxed to 0.75 m.
5. Spawn-inside change initially deadlocked the door jam demo; queue slots are now deterministic per agent (no swimming queues).

**Reproduce**
```
python tools/bench_physics.py rush         # ticks/s at ~250 agents
python tools/bench_physics.py bottleneck   # door density vs shop
python -m pytest backend/tests -q
python -m uvicorn app.main:app --port 8000 # CROWD_GHOST_LEVEL selects level
```

**Declared limitations**
- Agents in a jam push each other out the entrance door and wander the enclosed forecourt — physically plausible; they re-enter when the gap clears.
- The crowd model has no group behavior, panic waves, or density-dependent speed beyond the social-force repulsion ramp.
