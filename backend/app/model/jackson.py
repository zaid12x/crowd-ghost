"""Open Jackson queueing network.

Museum model: N rooms (stations). External Poisson arrivals gamma_i enter
room i directly. Each room i has c_i parallel servers (exhibit/door capacity),
exponential service rate mu_i. A customer leaving room i routes to room j
with probability P[i][j]; the remainder 1 - rowsum(P[i]) leaves the network
(exit).

Traffic equations:  lambda = gamma + P^T lambda
                    lambda = (I - P^T)^(-1) gamma        (requires rho(P) < 1)

Per room, M/M/c:  a = lambda / mu                (offered load)
                  rho = lambda / (c * mu)         (require rho < 1)
                  ErlangC: P(wait>0)
                  Wq = Pwait / (c*mu - lambda)
                  Lq = lambda * Wq ;  W = Wq + 1/mu ;  L = lambda * W
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

TOL = 1e-9


@dataclass
class NetworkConfig:
    gamma: np.ndarray   # external arrival rate per room (per minute)
    mu: np.ndarray      # service rate per server per room
    c: np.ndarray       # servers per room (integers)
    P: np.ndarray       # routing matrix, row i -> col j

    def __post_init__(self):
        self.gamma = np.asarray(self.gamma, dtype=np.float64)
        self.mu = np.asarray(self.mu, dtype=np.float64)
        self.c = np.asarray(self.c, dtype=np.int64)
        self.P = np.asarray(self.P, dtype=np.float64)
        n = len(self.gamma)
        if self.mu.shape != (n,) or self.c.shape != (n,):
            raise ValueError("mu and c must match gamma length")
        if self.P.shape != (n, n):
            raise ValueError(f"P must be square {n}x{n}, got {self.P.shape}")
        validate_routing(self.P)
        if np.any(self.mu <= 0):
            raise ValueError("mu must be positive")
        if np.any(self.c < 1):
            raise ValueError("each room needs at least 1 server")
        if np.any(self.gamma < 0):
            raise ValueError("gamma must be non-negative")


def validate_routing(P: np.ndarray) -> None:
    P = np.asarray(P, dtype=np.float64)
    if P.ndim != 2 or P.shape[0] != P.shape[1]:
        raise ValueError("P must be square")
    if np.any(P < -TOL):
        raise ValueError("P contains negative entries")
    rowsums = P.sum(axis=1)
    if np.any(rowsums > 1.0 + 1e-9):
        bad = int(np.argmax(rowsums > 1.0 + 1e-9))
        raise ValueError(f"routing row {bad} sums to {rowsums[bad]:.6f} > 1 (remainder must be exit probability; >= 0)")
    # open network needs a path to an exit: spectral radius < 1
    eig = np.max(np.abs(np.linalg.eigvals(P)))
    if eig >= 1.0 - 1e-12:
        raise ValueError(f"routing matrix has spectral radius {eig:.6f} >= 1 — no exit path; network is closed/unstable")


def solve_traffic(P: np.ndarray, gamma: np.ndarray) -> np.ndarray:
    """lambda = (I - P^T)^-1 gamma ; verifies the equation to 1e-9."""
    lam = np.linalg.solve(np.eye(P.shape[0]) - P.T, gamma)
    residual = np.linalg.norm(lam - gamma - P.T @ lam, ord=np.inf)
    if residual > 1e-9:
        raise ArithmeticError(f"traffic equations not satisfied, residual={residual}")
    return lam


def erlang_c(a: float, c: int) -> float:
    """P(wait > 0) for an M/M/c queue with offered load a = lambda/mu."""
    if a <= 0:
        return 0.0
    # log-sum-exp computation of sum_{k=0}^{c-1} a^k / k!
    terms = [k * math.log(a) - math.lgamma(k + 1) for k in range(c)]
    max_term = max(terms)
    sum_prev = math.exp(max_term) * sum(math.exp(t - max_term) for t in terms)
    log_pc = c * math.log(a) - math.lgamma(c + 1)
    pc = math.exp(log_pc)
    if c * 1.0 - a <= 0:  # unstable, guarded upstream by rho < 1
        return 1.0
    wait_term = pc * c / (c - a)
    return wait_term / (sum_prev + wait_term)


@dataclass
class StationStats:
    lam: float       # solved arrival rate
    rho: float       # utilization
    offered: float   # a = lambda / mu
    erlang_c: float  # P(wait > 0)
    wq: float        # mean queue wait (min)
    lq: float        # mean number queueing
    w: float         # mean total time in system
    l: float         # mean number in system


def analyze_station(lam: float, mu: float, c: int, name: str = "room") -> StationStats:
    if lam < 0:
        raise ValueError("lambda must be non-negative")
    if c < 1:
        raise ValueError("c must be >= 1")
    rho = lam / (c * mu)
    if rho >= 1.0:
        raise ValueError(f"{name}: rho = {rho:.4f} >= 1 — queue is unstable (lambda={lam:.4f}, c*mu={c*mu:.4f}). Reduce arrival rate, add capacity or service rate.")
    a = lam / mu
    pc = erlang_c(a, c)
    wq = pc / (c * mu - lam) if (c * mu - lam) > 0 else math.inf
    lq = lam * wq
    w = wq + 1.0 / mu
    l = lam * w
    return StationStats(lam=lam, rho=rho, offered=a, erlang_c=pc, wq=wq, lq=lq, w=w, l=l)


def analyze(cfg: NetworkConfig) -> list[StationStats]:
    lam = solve_traffic(cfg.P, cfg.gamma)
    return [analyze_station(lam[i], cfg.mu[i], int(cfg.c[i]), name=f"room {i}") for i in range(len(lam))]


def network_summary(stats: list[StationStats]) -> dict:
    total_wq = sum(s.lam * s.wq for s in stats) / max(sum(s.lam for s in stats), TOL)
    return {
        "mean_wait_weighted": total_wq,
        "max_rho": max(s.rho for s in stats),
        "total_lq": sum(s.lq for s in stats),
        "total_l": sum(s.l for s in stats),
    }
