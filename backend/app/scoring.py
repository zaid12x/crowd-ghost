"""Score = f(mean wait, rooms seen, crush index). Pure, documented, checkable.

score = clamp(100 - 12 * mean_wait_s - 150 * crush_frac + 4 * min(rooms_seen, 5), 0, 100)

- mean_wait_s  : mean queue wait per exit, measured live by the engine
                 (total_queue_time / exited — not a model prediction).
- crush_frac   : fraction of agent-seconds spent in rooms above CRUSH_DENSITY
                 (4 agents/m^2). Measured live from polygon areas (shoelace).
- rooms_seen   : expected rooms visited per visitor from the Markov routing
                 matrix (app.optimize.objective.rooms_seen_mean), rewarding
                 flow over dead-end layouts — up to +20 points (cap 5).

Weights are a design choice, not derived truth; they are stated here once and
used identically by the live endpoint, the CLI and the ghost card. Evacuation
levels (fire drill) are scored on time-to-clear instead — no queueing model
applies, so the same formula would be a lie.
"""

from __future__ import annotations

WEIGHT_WAIT = 12.0        # points lost per second of mean queue wait
WEIGHT_CRUSH = 150.0      # points lost per unit of crush fraction (0..1)
ROOMS_SEEN_BONUS = 4.0    # points per room seen per visitor
ROOMS_SEEN_CAP = 5.0      # rooms-seen contribution caps at +20


def crush_fraction(crush_seconds: float, agent_seconds: float) -> float:
    return crush_seconds / agent_seconds if agent_seconds > 0.0 else 0.0


def score_queueing(mean_wait_s: float, crush_frac: float, rooms_seen: float) -> int:
    raw = (
        100.0
        - WEIGHT_WAIT * max(0.0, mean_wait_s)
        - WEIGHT_CRUSH * max(0.0, crush_frac)
        + ROOMS_SEEN_BONUS * min(max(rooms_seen, 0.0), ROOMS_SEEN_CAP)
    )
    return int(round(min(100.0, max(0.0, raw))))
