"""Truncated birth-death CTMC for one M/M/c station.

Used by the UI to answer "how fast does the queue build after a surge" —
the transient distribution pi(t) = p0 * expm(Q t), where Q is the generator
of the birth-death chain truncated at k_max customers.

Birth rate in state n:  lambda (arrivals, constant)
Death rate in state n:  min(n, c) * mu
The truncation reflects at k_max (birth suppressed at the ceiling).
"""

from __future__ import annotations

import numpy as np
from scipy.linalg import expm


def birth_death_generator(lam: float, mu: float, c: int, k_max: int = 60) -> np.ndarray:
    n = k_max + 1
    Q = np.zeros((n, n))
    for i in range(n):
        birth = lam if i < k_max else 0.0
        death = min(i, c) * mu if i > 0 else 0.0
        if i + 1 < n:
            Q[i, i + 1] = birth
        if i - 1 >= 0:
            Q[i, i - 1] = death
        Q[i, i] = -(birth + death)
    return Q


def transient(lam: float, mu: float, c: int, k_max: int, t: float, p0: np.ndarray | None = None) -> np.ndarray:
    Q = birth_death_generator(lam, mu, c, k_max)
    if p0 is None:
        p0 = np.zeros(k_max + 1)
        p0[0] = 1.0
    return p0 @ expm(Q * t)


def expected_length_series(lam: float, mu: float, c: int, k_max: int, times: np.ndarray) -> np.ndarray:
    """E[N(t)] (number in system) at each time in `times`, starting empty."""
    Q = birth_death_generator(lam, mu, c, k_max)
    expm_t = {ti: expm(Q * float(ti)) for ti in np.unique(times)}
    p0 = np.zeros(k_max + 1)
    p0[0] = 1.0
    idx = np.arange(k_max + 1)
    out = []
    for ti in times:
        pi = p0 @ expm_t[float(ti)]
        out.append(float(pi @ idx))
    return np.array(out)


def stationary(lam: float, mu: float, c: int, k_max: int = 200) -> np.ndarray:
    """Stationary distribution = normalized eigenvector for eigenvalue 0 of Q^T."""
    Q = birth_death_generator(lam, mu, c, k_max)
    w, v = np.linalg.eig(Q.T)
    i = int(np.argmin(np.abs(w)))
    pi = np.real(v[:, i])
    pi = np.abs(pi)
    return pi / pi.sum()
