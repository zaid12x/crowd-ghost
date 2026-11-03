import numpy as np

from app.model.ctmc import birth_death_generator, transient, stationary


def test_generator_row_sums_zero():
    Q = birth_death_generator(0.5, 1.0, c=1, k_max=10)
    assert np.allclose(Q.sum(axis=1), 0.0, atol=1e-12)


def test_stationary_matches_geometric_mm1():
    # M/M/1 stationary: pi_n = (1 - rho) rho^n, rho = 0.5
    lam, mu = 0.5, 1.0
    pi = stationary(lam, mu, c=1, k_max=60)
    rho = lam / mu
    expected = (1 - rho) * rho ** np.arange(len(pi))
    expected /= expected.sum()
    assert np.allclose(pi, expected, atol=1e-9)


def test_transient_distribution_normalized():
    pi = transient(0.5, 1.0, c=1, k_max=30, t=2.0)
    assert abs(pi.sum() - 1.0) < 1e-9
    assert np.all(pi >= -1e-12)


def test_transient_empty_start_builds_queue():
    early = transient(0.5, 1.0, c=1, k_max=30, t=0.1)
    late = transient(0.5, 1.0, c=1, k_max=30, t=30.0)
    assert early[0] > late[0]  # probability of empty system decays toward (1-rho)
    assert late[0] < 0.55      # stationary pi_0 = 0.5
