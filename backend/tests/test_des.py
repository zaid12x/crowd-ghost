import numpy as np

from app.model.jackson import NetworkConfig
from app.model import des


def _cfg(gamma0: float) -> NetworkConfig:
    return NetworkConfig(
        gamma=np.array([gamma0, 0.0, 0.0, 0.0]),
        mu=np.array([1.0, 1.0, 1.0, 1.0]),
        c=np.array([2, 1, 1, 1]),
        P=np.array([
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 0.9, 0.0],
            [0.0, 0.0, 0.0, 0.8],
            [0.0, 0.0, 0.0, 0.0],
        ]),
    )


def test_des_deterministic_given_seed():
    a = des.run(_cfg(0.4), seed=42, t_end=2000)
    b = des.run(_cfg(0.4), seed=42, t_end=2000)
    assert a[0]["mean_wait"] == b[0]["mean_wait"]


def test_des_higher_load_waits_longer():
    light = des.run(_cfg(0.2), seed=1, t_end=4000)
    heavy = des.run(_cfg(0.85), seed=1, t_end=4000)
    assert heavy[1]["mean_wait"] > light[1]["mean_wait"]  # Gallery A is the bottleneck gate


def test_des_all_nodes_served():
    res = des.run(_cfg(0.4), seed=3, t_end=3000)
    for i in range(4):
        assert res[i]["customers"] > 100
    assert res["_meta"]["external_exits"] > 100
