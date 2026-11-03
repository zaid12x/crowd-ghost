import numpy as np

from app.protocol import encode_frame, decode_frame
from app.sim_loop import SimState


def test_frame_roundtrip():
    agents = np.array([[1.0, 2.0, 0.5, -0.5], [3.0, 4.0, 1.0, 0.0]], dtype=np.float32)
    rooms = np.array([[2.0, 0.8, 12.5]], dtype=np.float32)
    data = encode_frame(42, agents, rooms, flags=1)
    tick, flags, a, r = decode_frame(data)
    assert tick == 42
    assert flags == 1
    assert np.allclose(a, agents)
    assert np.allclose(r, rooms)


def test_sim_ticks():
    sim = SimState(n_agents=10)
    t0 = sim.tick
    for _ in range(30):
        sim.update()
    assert sim.tick == t0 + 30
    assert len(sim.agents) == 10
    w, h = sim.bounds
    assert np.all(sim.agents[:, 0] >= 0) and np.all(sim.agents[:, 0] <= w)
    assert np.all(sim.agents[:, 1] >= 0) and np.all(sim.agents[:, 1] <= h)
