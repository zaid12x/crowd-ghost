"""Floorplan: rooms (polygons), walls (segments), doors (gaps).

Design contract for level JSON:
  - rooms: rectangles/polygons (axis-aligned edges recommended)
  - doors: centered ON a wall line (|perp distance| < snap), axis aligned
      angle = 0  -> door crosses a HORIZONTAL wall (gap along x)
      angle = 90 -> door crosses a VERTICAL wall   (gap along y)
  - doors with rooms: [a, b] connect a<->b; [null, b] entrance to b; [a, null] exit from a
Solid wall segments are auto-derived by subtracting door gaps from room edges.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

import numpy as np


def _seg_nearest_batch_np(pts: np.ndarray, ax, ay, bx, by):
    px, py = pts[:, 0], pts[:, 1]
    vx, vy = bx - ax, by - ay
    wx, wy = px - ax, py - ay
    len2 = vx * vx + vy * vy
    if len2 == 0.0:
        d = np.hypot(px - ax, py - ay)
        return d, np.full_like(d, ax), np.full_like(d, ay)
    t = np.clip((wx * vx + wy * vy) / len2, 0.0, 1.0)
    qx, qy = ax + t * vx, ay + t * vy
    return np.hypot(px - qx, py - qy), qx, qy


def point_in_polygon(x: float, y: float, poly: list[list[float]]) -> bool:
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y):
            x_int = xi + (y - yi) * (xj - xi) / (yj - yi)
            if x < x_int:
                inside = not inside
        j = i
    return inside


def _seg_subtract(p0, p1, gaps):
    """Subtract overlapping gap intervals from segment (p0,p1) (axis-aligned)."""
    if gaps:
        horiz = abs(p0[1] - p1[1]) < 1e-9
        axis = 0 if horiz else 1
        lo, hi = sorted([p0[axis], p1[axis]])
        intervals = []
        for g0, g1 in sorted(gaps):
            g0, g1 = max(g0, lo), min(g1, hi)
            if g0 < g1:
                intervals.append((g0, g1))
        # build solid pieces
        pieces = []
        cur = lo
        for g0, g1 in intervals:
            if cur < g0:
                if horiz:
                    pieces.append([[cur, p0[1]], [g0, p0[1]]])
                else:
                    pieces.append([[p0[0], cur], [p0[0], g0]])
            cur = max(cur, g1)
        if cur < hi:
            if horiz:
                pieces.append([[cur, p0[1]], [hi, p0[1]]])
            else:
                pieces.append([[p0[0], cur], [p0[0], hi]])
        return pieces
    return [[list(p0), list(p1)]]


@dataclass
class Room:
    id: int
    name: str
    polygon: list[list[float]]
    capacity: int
    mu: float          # service rate (1/seconds)
    dwell: float = 3.0 # mean dwell seconds (visual pacing)

    @property
    def centroid(self):
        arr = np.array(self.polygon, dtype=float)
        return arr.mean(axis=0)


@dataclass
class Door:
    id: str
    rooms: tuple         # (a_index | None, b_index | None)
    x: float
    y: float
    angle: float         # 0 horizontal wall, 90 vertical wall
    width: float

    @property
    def center(self):
        return np.array([self.x, self.y], dtype=float)

    def other_room(self, room_id: int):
        a, b = self.rooms
        if a == room_id:
            return b
        if b == room_id:
            return a
        return None


@dataclass
class Floorplan:
    bounds: tuple[float, float]
    rooms: list[Room]
    doors: list[Door]
    walls: list[list[list[float]]] = field(default_factory=list)

    @classmethod
    def from_json(cls, path: str) -> "Floorplan":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> "Floorplan":
        rooms = [
            Room(
                id=r["id"], name=r.get("name", f"room{r['id']}"),
                polygon=[list(map(float, p)) for p in r["polygon"]],
                capacity=int(r["capacity"]), mu=float(r["mu"]),
                dwell=float(r.get("dwell", 3.0)),
            )
            for r in data["rooms"]
        ]
        doors = [
            Door(id=d["id"], rooms=tuple(d["rooms"]), x=float(d["x"]), y=float(d["y"]),
                 angle=float(d["angle"]), width=float(d["width"]))
            for d in data["doors"]
        ]
        fp = cls(bounds=tuple(map(float, data["bounds"])), rooms=rooms, doors=doors)
        fp.derive_walls()
        return fp

    def derive_walls(self):
        edges: list[list[list[float]]] = []
        for room in self.rooms:
            poly = room.polygon
            n = len(poly)
            for i in range(n):
                edges.append([list(poly[i]), list(poly[(i + 1) % n])])
        solid: list[list[list[float]]] = []
        for edge in edges:
            p0, p1 = np.array(edge[0], dtype=float), np.array(edge[1], dtype=float)
            horiz = abs(p0[1] - p1[1]) < 1e-9
            vertical = abs(p0[0] - p1[0]) < 1e-9
            if not (horiz or vertical):
                solid.append([p0.tolist(), p1.tolist()])  # keep diagonal as-is
                continue
            gaps = []
            for d in self.doors:
                if horiz and abs(d.angle) < 1e-6 and abs(d.y - p0[1]) < 0.75:
                    axis = 0
                elif vertical and abs(d.angle - 90) < 1e-6 and abs(d.x - p0[0]) < 0.75:
                    axis = 1
                else:
                    continue
                c = d.x if axis == 0 else d.y
                # gap must overlap this edge's span
                lo, hi = (sorted([p0[axis], p1[axis]]))
                if c + d.width / 2 <= lo or c - d.width / 2 >= hi:
                    continue
                gaps.append((c - d.width / 2, c + d.width / 2))
            solid.extend(_seg_subtract(p0.tolist(), p1.tolist(), gaps))
        solid.extend(self._perimeter_walls())
        self.walls = solid

    def _perimeter_walls(self) -> list[list[list[float]]]:
        """Closed perimeter around the site (bounds rectangle), split at external doors."""
        W, H = self.bounds
        base = [[[0.0, 0.0], [W, 0.0]], [[W, 0.0], [W, H]], [[W, H], [0.0, H]], [[0.0, H], [0.0, 0.0]]]
        out: list[list[list[float]]] = []
        for seg in base:
            p0, p1 = np.array(seg[0], dtype=float), np.array(seg[1], dtype=float)
            horiz = abs(p0[1] - p1[1]) < 1e-9
            gaps = []
            for d in self.doors:
                external = (d.rooms[0] is None) or (d.rooms[1] is None)
                if not external:
                    continue
                if horiz and abs(d.angle) < 1e-6 and abs(d.y - p0[1]) < 0.75:
                    axis = 0
                elif not horiz and abs(d.angle - 90) < 1e-6 and abs(d.x - p0[0]) < 0.75:
                    axis = 1
                else:
                    continue
                c = d.x if axis == 0 else d.y
                lo, hi = sorted([p0[axis], p1[axis]])
                if c + d.width / 2 <= lo or c - d.width / 2 >= hi:
                    continue
                gaps.append((c - d.width / 2, c + d.width / 2))
            out.extend(_seg_subtract(p0.tolist(), p1.tolist(), gaps))
        return out

    def room_at(self, x: float, y: float):
        for room in self.rooms:
            if point_in_polygon(x, y, room.polygon):
                return room
        return None

    def mask_inside(self, pts: np.ndarray) -> np.ndarray:
        """True where a point is inside the site and clear of every wall (no tunnelling/embedded agents)."""
        W, H = self.bounds
        mask = (pts[:, 0] >= 0.1) & (pts[:, 0] <= W - 0.1) & (pts[:, 1] >= 0.1) & (pts[:, 1] <= H - 0.1)
        for w in self.walls:
            ax, ay = w[0]
            bx, by = w[1]
            d, _, _ = _seg_nearest_batch_np(pts, ax, ay, bx, by)
            mask &= d > 0.15
        return mask

    def walls_np(self):
        return (
            np.array([w[0] for w in self.walls], dtype=np.float64),
            np.array([w[1] for w in self.walls], dtype=np.float64),
        )
