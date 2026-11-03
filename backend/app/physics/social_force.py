"""Helbing social-force crowd engine.

Vectorised agent-agent and agent-wall forces with a spatial hash; per-agent
state machine handles rooms, doors (capacity-enforced — agents queue outside
a full room), dwelling and exits. Deterministic given a seed.

Units: seconds, meters. gamma = expected spawns/second, mu = service rate
(1/seconds) per room (dwell ~ exponential(mean=1/mu * dwell_scale)).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from app.physics.floorplan import Door, Floorplan, point_in_polygon

DT = 1.0 / 30.0
SUBSTEPS = 2
AGENT_RADIUS = 0.25
TAU = 0.5
A_SOC = 12.0        # social repulsion strength (m/s^2)
B_SOC = 0.28        # social repulsion range (m)
A_WALL = 18.0
B_WALL = 0.22
WALL_RANGE = 0.55
CELL = 1.5
INTERACT = 1.6


@dataclass
class Agent:
    id: int
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    state: str = "walk"        # walk | queue | dwelling | gone
    room: int | None = None    # index into floorplan.rooms
    target_door: Door | None = None
    goal_room: int | None = None
    exiting: bool = False
    dwell_left: float = 0.0
    dwell_x: float = 0.0
    dwell_y: float = 0.0
    queue_slot: int = 0
    queue_since: float | None = None


def _p_choice(P: np.ndarray, room: int, rng: np.random.Generator):
    row = P[room]
    r = rng.random()
    cum = 0.0
    for j, p in enumerate(row):
        cum += p
        if r <= cum:
            return int(j)
    return None


def _seg_nearest_batch(px, py, ax, ay, bx, by):
    """Vectorized: for points (px,py) arrays, return (dist, qx, qy) to segment a-b."""
    vx, vy = bx - ax, by - ay
    wx, wy = px - ax, py - ay
    len2 = vx * vx + vy * vy
    if len2 == 0.0:
        d = np.hypot(px - ax, py - ay)
        return d, np.full_like(d, ax), np.full_like(d, ay)
    t = np.clip((wx * vx + wy * vy) / len2, 0.0, 1.0)
    qx, qy = ax + t * vx, ay + t * vy
    d = np.hypot(px - qx, py - qy)
    return d, qx, qy


class PhysicsEngine:
    def __init__(self, level: dict, seed: int = 0, max_agents: int | None = None):
        self.level = level
        self.fp = Floorplan.from_dict(level)
        self.P = np.array(level.get("P", np.eye(len(self.fp.rooms))), dtype=float)
        self.gamma = float(level.get("gamma", 1.0))
        self.evacuation = bool(level.get("evacuation", False))
        self.max_agents = int(max_agents or level.get("max_agents", 300))
        self.v0 = float(level.get("v0", 1.3))
        self.rng = np.random.default_rng(seed)
        self.agents: list[Agent] = []
        self.time = 0.0
        self._spawn_in = 1.0
        self.spawned = 0
        self.exited = 0
        self.admissions = {r.id: 0 for r in self.fp.rooms}
        self._adm_tick = {r.id: 0 for r in self.fp.rooms}
        self._lam_rate = {r.id: 0.0 for r in self.fp.rooms}
        self.entrance = next(d for d in self.fp.doors if d.rooms[0] is None)
        self.exits = [d for d in self.fp.doors if d.rooms[1] is None]
        self._next_id = 0
        self.waiting_total = 0
        self.peak_waiting = 0
        self.total_queue_time = 0.0
        # door admission rate: width * 1.3 persons/second (single-file flow)
        self.door_rate = {d.id: d.width * 1.3 for d in self.fp.doors}
        self.door_tokens = {d.id: d.width * 1.3 for d in self.fp.doors}
        self._walls_arr = np.array(
            [(w[0][0], w[0][1], w[1][0], w[1][1]) for w in self.fp.walls], dtype=float
        ) if self.fp.walls else np.zeros((0, 4))
        for _ in range(int(level.get("prefill", 0))):
            self._prefill_agent()

    # ---------- helpers ----------
    def occupancy(self) -> list[int]:
        occ = [0] * len(self.fp.rooms)
        for a in self.agents:
            if a.room is not None:
                occ[a.room] += 1
        return occ

    def _dwell_point(self, room) -> tuple[float, float]:
        poly = room.polygon
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        for _ in range(48):
            x = self.rng.uniform(min(xs) + 1.0, max(xs) - 1.0)
            y = self.rng.uniform(min(ys) + 1.0, max(ys) - 1.0)
            if point_in_polygon(x, y, poly):
                return x, y
        c = room.centroid
        return float(c[0]), float(c[1])

    def _axis(self, door: Door) -> int:
        return 0 if abs(door.angle) < 1e-6 else 1

    def _side_sign(self, door: Door, room_id: int) -> float:
        c = self.fp.rooms[room_id].centroid
        idx = self._axis(door)
        return 1.0 if c[idx] >= (door.y if idx == 1 else door.x) else -1.0

    def queue_slot_pos(self, door: Door, from_room: int, slot: int, agent_id: int) -> np.ndarray:
        """Deterministic queue slot: behind the door on the waiting room's side."""
        sign = self._side_sign(door, from_room)
        back = 0.85 + 0.36 * slot
        lat = (((agent_id * 2654435761) & 0xFFFFFFFF) / 0xFFFFFFFF - 0.5) * 0.55
        if self._axis(door) == 0:  # horizontal wall: slot behind along y
            return np.array([door.x + lat, door.y + sign * back])
        return np.array([door.x + sign * back, door.y + lat])

    def _exit_plan(self, room_id: int) -> list[Door]:
        """Breadth-first path from a room to an exit: list of doors to walk through."""
        cache = getattr(self, "_exit_plan_cache", {})
        if room_id in cache:
            return cache[room_id]
        from collections import deque

        queue = deque([(room_id, [])])
        visited = {room_id}
        plan = None
        while queue:
            cur, path = queue.popleft()
            for d in self.exits:
                if d.rooms[0] == cur:
                    plan = path + [d]
                    break
            if plan is not None:
                break
            for d in self.fp.doors:
                nxt = d.other_room(cur)
                if nxt is None or nxt in visited:
                    continue
                visited.add(nxt)
                queue.append((nxt, path + [d]))
        if plan is None:
            plan = [self.exits[0]]
        cache[room_id] = plan
        self._exit_plan_cache = cache
        return plan

    def _enter_room(self, a: Agent, room_id: int):
        a.room = room_id
        self.admissions[room_id] += 1
        self._adm_tick[room_id] += 1
        room = self.fp.rooms[room_id]
        a.dwell_left = max(room.dwell * self.rng.exponential(), 0.15)
        a.dwell_x, a.dwell_y = self._dwell_point(room)
        a.state = "dwelling"
        if self.evacuation:
            a.exiting = True
            a.goal_room = None
            a.target_door = self._exit_plan(room_id)[0]

    def _assign_next(self, a: Agent):
        """After dwelling: pick next room via P, or exit. Evacuation -> straight to exit."""
        nxt = None
        if not self.evacuation and a.room is not None:
            nxt = _p_choice(self.P, a.room, self.rng)
        if nxt is None:
            door = next((d for d in self.fp.doors if d.rooms[0] == a.room and d.rooms[1] is None), self.exits[0])
            a.target_door, a.exiting, a.goal_room = door, True, None
        else:
            door = next(d for d in self.fp.doors
                        if (d.rooms[0] == a.room and d.rooms[1] == nxt) or (d.rooms[0] == nxt and d.rooms[1] == a.room))
            a.target_door, a.exiting, a.goal_room = door, False, nxt
        a.state = "walk"

    # ---------- prefill (fire drill: the crowd starts inside) ----------
    def _prefill_agent(self):
        room_ids = list(range(len(self.fp.rooms)))
        room_id = int(self.rng.choice(room_ids))
        room = self.fp.rooms[room_id]
        x, y = self._dwell_point(room)
        a = Agent(id=self._next_id, x=x, y=y, vx=0.0, vy=0.0, state="dwelling",
                  room=room_id, dwell_left=self.rng.uniform(0.2, 2.5))
        a.dwell_x, a.dwell_y = x, y
        self._next_id += 1
        self.agents.append(a)
        self.spawned += 1

    # ---------- spawning ----------
    def _spawn(self):
        d = self.entrance
        idx = self._axis(d)
        sign = self._side_sign(d, d.rooms[1])  # toward the room interior
        if idx == 0:
            x, y = d.x + self.rng.uniform(-d.width / 3, d.width / 3), d.y + sign * 0.5
            vx, vy = 0.0, sign * self.v0
        else:
            x, y = d.x + sign * 0.5, d.y + self.rng.uniform(-d.width / 3, d.width / 3)
            vx, vy = sign * self.v0, 0.0
        a = Agent(id=self._next_id, x=x, y=y, vx=vx, vy=vy, state="walk", room=None)
        self._next_id += 1
        self.agents.append(a)
        self.spawned += 1
        self._enter_room(a, d.rooms[1])  # admission into the entrance room
        a.state = "dwelling"

    # ---------- main step ----------
    def step(self, dt: float = DT):
        self.time += dt
        self._spawn_in -= dt
        if self._spawn_in <= 0:
            if len(self.agents) < self.max_agents:
                self._spawn()
            self._spawn_in = self.rng.exponential(1.0 / max(self.gamma, 1e-6))

        # EMA of admissions -> per-second rate estimate per room
        alpha = 1.0 - math.exp(-dt / 8.0)
        for k in self._lam_rate:
            rate_now = self._adm_tick[k] / dt
            self._lam_rate[k] = (1.0 - alpha) * self._lam_rate[k] + alpha * rate_now
            self._adm_tick[k] = 0

        # door admission rate: width * 1.3 persons/second (single-file flow)
        for d_id, rate in self.door_rate.items():
            self.door_tokens[d_id] = min(self.door_tokens[d_id] + rate * dt, rate)

        occupancy = self.occupancy()
        sub_dt = dt / SUBSTEPS
        for _ in range(SUBSTEPS):
            self._forces_and_integrate(sub_dt, occupancy)
        self._door_transitions()

        self.agents = [a for a in self.agents if a.state != "gone"]
        self.waiting_total = sum(1 for a in self.agents if a.state == "queue")
        self.peak_waiting = max(self.peak_waiting, self.waiting_total)
        return self

    # ---------- dynamics ----------
    def _goal_vector(self, i: int, a: Agent, pos: np.ndarray):
        if a.state == "dwelling":
            anchor = np.array([a.dwell_x, a.dwell_y])
            d = np.linalg.norm(anchor - pos[i])
            if d < 0.35:
                return np.array([math.cos(a.id * 2.39996), math.sin(a.id * 2.39996)]) * 0.08, 0.08
            return (anchor - pos[i]) / d, 0.75
        if a.state == "queue":
            slot = self.queue_slot_pos(a.target_door, a.room, a.queue_slot, a.id)
            d = np.linalg.norm(slot - pos[i])
            if d < 0.22:
                return np.zeros(2), 0.0
            return (slot - pos[i]) / d, 0.85
        tgt = a.target_door.center if a.target_door is not None else self.fp.rooms[a.goal_room or 0].centroid
        d = np.linalg.norm(tgt - pos[i]) + 1e-9
        return (tgt - pos[i]) / d, self.v0

    def _forces_and_integrate(self, dt, occupancy):
        n = len(self.agents)
        if n == 0:
            return
        pos = np.array([[a.x, a.y] for a in self.agents])
        vel = np.array([[a.vx, a.vy] for a in self.agents])

        desired = np.zeros((n, 2))
        speed_des = np.zeros(n)
        for i, a in enumerate(self.agents):
            desired[i], speed_des[i] = self._goal_vector(i, a, pos)
        acc = (desired * speed_des[:, None] - vel) / TAU

        # agent-agent repulsion (spatial hash)
        grid: dict[tuple[int, int], list[int]] = {}
        for i, p in enumerate(pos):
            grid.setdefault((int(p[0] // CELL), int(p[1] // CELL)), []).append(i)
        for i, p in enumerate(pos):
            cx, cy = int(p[0] // CELL), int(p[1] // CELL)
            for gx in range(cx - 1, cx + 2):
                for gy in range(cy - 1, cy + 2):
                    for j in grid.get((gx, gy), ()):
                        if j <= i:
                            continue
                        diff = pos[i] - pos[j]
                        d = float(np.linalg.norm(diff))
                        if d < 1e-6:
                            ang = (i * 12.9898 + j * 78.233) % (2 * math.pi)
                            diff = np.array([math.cos(ang), math.sin(ang)])
                            d = 1e-6
                        if d < INTERACT:
                            f = A_SOC * math.exp((2 * AGENT_RADIUS - d) / B_SOC)
                            u = diff / d
                            acc[i] += f * u
                            acc[j] -= f * u

        # wall repulsion (vectorized per wall)
        if len(self._walls_arr):
            for ax, ay, bx, by in self._walls_arr:
                d, qx, qy = _seg_nearest_batch(pos[:, 0], pos[:, 1], ax, ay, bx, by)
                hit = d < WALL_RANGE
                if not np.any(hit):
                    continue
                idx = np.where(hit)[0]
                dd = np.maximum(d[idx], 1e-4)
                nrm = (pos[idx] - np.stack([qx[idx], qy[idx]], axis=1)) / dd[:, None]
                fmag = A_WALL * np.exp((AGENT_RADIUS - d[idx]) / B_WALL)
                pen = AGENT_RADIUS - d[idx]
                fmag = fmag + np.where(pen > 0, 26.0 * pen / AGENT_RADIUS, 0.0)
                acc[idx] += fmag[:, None] * nrm

        vel2 = vel + acc * dt
        speed = np.linalg.norm(vel2, axis=1, keepdims=True)
        scale = np.where(speed > 2.1, 2.1 / np.maximum(speed, 1e-9), 1.0)
        vel2 = vel2 * scale
        pos2 = pos + vel2 * dt
        W, H = self.fp.bounds
        pos2[:, 0] = np.clip(pos2[:, 0], 0.15, W - 0.15)
        pos2[:, 1] = np.clip(pos2[:, 1], 0.15, H - 0.15)

        # hard de-penetration (kills tunneling)
        if len(self._walls_arr):
            for ax, ay, bx, by in self._walls_arr:
                d, qx, qy = _seg_nearest_batch(pos2[:, 0], pos2[:, 1], ax, ay, bx, by)
                idx = np.where(d < AGENT_RADIUS * 0.7)[0]
                for i in idx:
                    dd = max(d[i], 1e-4)
                    nrm = (pos2[i] - np.array([qx[i], qy[i]])) / dd
                    pos2[i] = np.array([qx[i], qy[i]]) + nrm * AGENT_RADIUS * 0.7
                    vn = float(np.dot(vel2[i], nrm))
                    if vn < 0:
                        vel2[i] -= nrm * vn

        for i, a in enumerate(self.agents):
            a.x, a.y = float(pos2[i, 0]), float(pos2[i, 1])
            a.vx, a.vy = float(vel2[i, 0]), float(vel2[i, 1])
            if a.state == "dwelling":
                a.dwell_left -= dt
                if a.dwell_left <= 0:
                    if self.evacuation:
                        a.target_door = self._exit_plan(a.room)[0] if a.room is not None else self.exits[0]
                        a.exiting, a.goal_room, a.state = True, None, "walk"
                    else:
                        self._assign_next(a)

    def _door_transitions(self):
        occupancy = self.occupancy()
        occ = list(occupancy)
        # stable slot assignment in queues
        door_waiting: dict[str, list[Agent]] = {}
        for a in self.agents:
            if a.state == "queue" and a.target_door is not None:
                door_waiting.setdefault(a.target_door.id, []).append(a)
        for lst in door_waiting.values():
            for idx, a in enumerate(lst):
                a.queue_slot = idx

        for a in self.agents:
            if a.state == "queue":
                nxt = a.goal_room
                if nxt is None or self.evacuation or occ[nxt] < self.fp.rooms[nxt].capacity:
                    self._account_queue_exit(a)
                    a.state = "walk"
                continue
            if a.state != "walk" or a.target_door is None:
                continue
            door = a.target_door
            reach = 0.75 if a.exiting else 0.6  # stepping through an exit counts sooner
            if math.hypot(a.x - door.x, a.y - door.y) < reach:
                if a.exiting:
                    self._account_queue_exit(a)
                    a.state = "gone"
                    self.exited += 1
                    continue
                nxt = a.goal_room
                if nxt is not None and (self.evacuation or occ[nxt] < self.fp.rooms[nxt].capacity):
                    if self.door_tokens.get(door.id, 0.0) >= 1.0:
                        self.door_tokens[door.id] -= 1.0
                        occ[nxt] += 1
                        self._enter_room(a, nxt)
                    # else: door saturated — agent keeps pressing (counts as door backpressure)
                else:
                    a.state = "queue"
                    a.queue_slot = len(door_waiting.get(door.id, ()))
                    a.queue_since = self.time

    def _account_queue_exit(self, a: Agent):
        if getattr(a, "queue_since", None) is not None:
            self.total_queue_time += self.time - a.queue_since
            a.queue_since = None

    def mean_queue_seconds_per_exit(self) -> float:
        return self.total_queue_time / max(self.exited, 1)

    # ---------- wire format ----------
    def frame_arrays(self):
        agents = np.array([[a.x, a.y, a.vx, a.vy] for a in self.agents], dtype=np.float32)
        if len(agents) == 0:
            agents = np.zeros((0, 4), dtype=np.float32)
        rooms = []
        for r in self.fp.rooms:
            lam = self._lam_rate.get(r.id, 0.0)
            denom = r.capacity * r.mu
            rho = lam / denom if denom > 0 else 0.0
            wq = rho / (denom - lam) if denom > lam > 0 else (999.0 if lam >= denom else 0.0)
            queue_len = sum(1 for a in self.agents if a.state == "queue" and a.goal_room == r.id)
            rooms.append([float(queue_len), float(min(max(rho, 0.0), 9.99)), float(wq)])
        return agents, np.array(rooms, dtype=np.float32)
