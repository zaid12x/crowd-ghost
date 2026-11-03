import numpy as np
import pytest

from app.model.jackson import (
    NetworkConfig,
    analyze,
    analyze_station,
    erlang_c,
    solve_traffic,
    validate_routing,
)

P_TANDEM = np.array([[0.0, 1.0], [0.0, 0.0]])


def test_mm1_closed_form():
    # M/M/1: rho=0.5, mu=2, lambda=1  ->  Wq = lambda / (mu*(mu-lambda)) = 0.5
    s = analyze_station(lam=1.0, mu=2.0, c=1, name="t")
    assert abs(s.rho - 0.5) < 1e-12
    assert abs(s.wq - 0.5) < 1e-12
    assert abs(s.erlang_c - 0.5) < 1e-12  # Erlang C reduces to rho for c=1
    assert abs(s.lq - 0.5) < 1e-12        # Lq = lambda*Wq = 0.5
    assert abs(s.w - 1.0) < 1e-12         # W = Wq + 1/mu = 0.5 + 0.5


def test_erlang_c_two_servers():
    # c=2, offered load a=1 -> Pw = 1/3 (hand-computed)
    assert abs(erlang_c(1.0, 2) - 1.0 / 3.0) < 1e-12
    assert abs(erlang_c(0.0, 3)) < 1e-12


def test_rho_at_or_above_one_raises():
    with pytest.raises(ValueError, match="rho"):
        analyze_station(lam=2.0, mu=1.0, c=2, name="overload")


def test_routing_row_sum_above_one_raises():
    with pytest.raises(ValueError, match="row 0"):
        validate_routing(np.array([[0.7, 0.5], [0.0, 0.0]]))


def test_routing_non_square_raises():
    with pytest.raises(ValueError, match="square"):
        validate_routing(np.array([[0.5, 0.5, 0.0], [0.0, 1.0, 0.2]]))


def test_routing_no_exit_path_raises():
    # closed chain: every row sums to 1 -> spectral radius 1 -> no exit
    with pytest.raises(ValueError, match="spectral radius"):
        validate_routing(np.array([[0.0, 1.0], [1.0, 0.0]]))


def test_traffic_equations_residual():
    cfg = NetworkConfig(
        gamma=np.array([0.5, 0.0, 0.0, 0.0]),
        mu=np.array([1.0, 1.0, 1.0, 1.0]),
        c=np.array([2, 1, 1, 1]),
        P=np.array([
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 0.9, 0.0],
            [0.0, 0.0, 0.0, 0.8],
            [0.0, 0.0, 0.0, 0.0],
        ]),
    )
    lam = solve_traffic(cfg.P, cfg.gamma)
    assert np.allclose(lam - cfg.gamma - cfg.P.T @ lam, 0.0, atol=1e-9)
    assert np.allclose(lam, [0.5, 0.5, 0.45, 0.36], atol=1e-12)


def test_tandem_network_analysis():
    cfg = NetworkConfig(
        gamma=np.array([0.5, 0.0]),
        mu=np.array([1.0, 1.0]),
        c=np.array([1, 1]),
        P=P_TANDEM,
    )
    stats = analyze(cfg)
    assert np.allclose([s.lam for s in stats], [0.5, 0.5], atol=1e-12)
    assert np.allclose([s.rho for s in stats], [0.5, 0.5], atol=1e-12)
