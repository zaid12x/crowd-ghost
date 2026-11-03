"""Binary wire protocol between server and client.

Frame layout (little-endian), one frame per tick:

    magic     4s   "CGF1"
    tick      I    uint32 tick counter
    n_agents  H    uint16
    n_rooms   H    uint16
    flags     H    uint16 bitfield (bit0: evacuation mode)
    reserved  H    uint16 (0)
    agents    n_agents * 4 float32   x, y, vx, vy
    rooms     n_rooms  * 3 float32   queue_len, rho, wait_est (seconds)
"""

import struct

import numpy as np

MAGIC = b"CGF1"
HEADER = struct.Struct("<4sIHHHH")


def encode_frame(tick: int, agents: np.ndarray, rooms: np.ndarray, flags: int = 0) -> bytes:
    n_agents = len(agents)
    n_rooms = len(rooms)
    header = HEADER.pack(MAGIC, tick & 0xFFFFFFFF, n_agents, n_rooms, flags, 0)
    body = np.ascontiguousarray(agents, dtype=np.float32).tobytes()
    room_bytes = np.ascontiguousarray(rooms, dtype=np.float32).tobytes() if n_rooms else b""
    return header + body + room_bytes


def decode_frame(data: bytes):
    magic, tick, n_agents, n_rooms, flags, _ = HEADER.unpack_from(data, 0)
    assert magic == MAGIC, "bad magic"
    offset = HEADER.size
    a_bytes = 4 * 4 * n_agents
    agents = np.frombuffer(data[offset:offset + a_bytes], dtype=np.float32).reshape(n_agents, 4)
    offset += a_bytes
    r_bytes = 3 * 4 * n_rooms
    rooms = np.frombuffer(data[offset:offset + r_bytes], dtype=np.float32).reshape(n_rooms, 3)
    return tick, flags, agents, rooms
