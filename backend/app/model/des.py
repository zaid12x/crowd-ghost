"""Event-driven (discrete event) simulation of the same Jackson network.

Independent implementation used to validate the analytical model.
FCFS queues, exponential inter-arrival and service times, routing by P.

Measures per-node *queueing* waiting time (arrival-at-room -> service start),
matching Erlang C's Wq. Only customers admitted after `warm_up` are counted.
"""

from __future__ import annotations

import heapq
from collections import deque

import numpy as np

ARRIVAL = 0
DEPARTURE = 1


def run(cfg, seed: int = 0, t_end: float | None = None, warm_up_frac: float = 0.1) -> dict:
    rng = np.random.default_rng(seed)
    n = len(cfg.gamma)
    gamma = np.asarray(cfg.gamma, dtype=float)
    mu = np.asarray(cfg.mu, dtype=float)
    c = [int(v) for v in cfg.c]
    P = np.asarray(cfg.P, dtype=float)

    if t_end is None:
        total_rate = max(float(gamma.sum()), 1e-9)
        t_end = 12000.0 / total_rate + 500.0  # ~12000 external customers
    warm_up = warm_up_frac * t_end

    heap: list[tuple[float, int, int, int]] = []
    seq = 0

    def push(t, kind, node):
        nonlocal seq
        heapq.heappush(heap, (t, seq, kind, node))
        seq += 1

    in_service = np.zeros(n, dtype=np.int64)
    queues: list[deque[float]] = [deque() for _ in range(n)]
    waits: list[list[float]] = [[] for _ in range(n)]
    served = np.zeros(n, dtype=np.int64)
    external_done = 0

    def admit_or_queue(t, j):
        """Customer becomes present at node j at time t."""
        if in_service[j] < c[j]:
            in_service[j] += 1
            if t >= warm_up:
                waits[j].append(0.0)
            push(t + rng.exponential(1.0 / mu[j]), DEPARTURE, j)
        else:
            queues[j].append(t)

    for i in range(n):
        if gamma[i] > 0:
            push(rng.exponential(1.0 / gamma[i]), ARRIVAL, i)

    while heap:
        t, _, kind, i = heapq.heappop(heap)
        if t > t_end:
            break  # warm-up/t_end reached; stop (heap may hold far-future arrivals)
        if kind == ARRIVAL:
            if gamma[i] > 0:  # external stream: schedule successor (bounded by t_end)
                nxt_t = t + rng.exponential(1.0 / gamma[i])
                if nxt_t <= t_end:
                    push(nxt_t, ARRIVAL, i)
            admit_or_queue(t, i)
        else:  # DEPARTURE
            served[i] += 1
            in_service[i] -= 1
            if queues[i]:  # admit next waiting customer
                t_arr = queues[i].popleft()
                wait = t - t_arr
                in_service[i] += 1
                if t >= warm_up:
                    waits[i].append(wait)
                push(t + rng.exponential(1.0 / mu[i]), DEPARTURE, i)
            row = P[i]
            r = rng.random()
            cum, nxt = 0.0, -1
            for j in range(n):
                cum += row[j]
                if r <= cum:
                    nxt = j
                    break
            if nxt == -1:
                external_done += 1  # left the network
            else:
                admit_or_queue(t, nxt)

    result = {}
    for i in range(n):
        result[i] = {
            "mean_wait": float(np.mean(waits[i])) if waits[i] else 0.0,
            "customers": int(served[i]),
            "wait_samples": int(len(waits[i])),
        }
    result["_meta"] = {"t_end": t_end, "warm_up": warm_up, "seed": seed, "external_exits": external_done}
    return result
