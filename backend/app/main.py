"""FastAPI app: HTTP + WebSocket endpoint (binary frames at 30 Hz)."""

import asyncio
import json
import os
import time
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.sim_loop import TICK_HZ, DT, SimState, LEVELS_DIR, load_level

app = FastAPI(title="CROWD GHOST", version="0.1.0")

_sim = SimState()
_last_step = 0.0  # monotonic timestamp of the shared sim's last physics step

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


@app.get("/api/health")
def health():
    return {"ok": True, **_sim.status()}


@app.get("/api/levels")
def levels():
    out = []
    for f in sorted(Path(LEVELS_DIR).glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            out.append({"id": data.get("id", f.stem), "name": data.get("name", f.stem)})
        except Exception:
            continue
    return {"levels": out}


@app.get("/api/geometry")
def geometry(id: str | None = None):
    """Wall segments, room polygons, doors for rendering — read from the level file."""
    from app.physics.floorplan import Floorplan

    level_id = id or _sim.level_id
    try:
        level = load_level(level_id)
    except FileNotFoundError:
        return JSONResponse({"error": f"unknown level '{level_id}'"}, status_code=404)
    fp = Floorplan.from_dict(level)
    return {
        "id": level_id,
        "bounds": level["bounds"],
        "walls": [[w[0][0], w[0][1], w[1][0], w[1][1]] for w in fp.walls],
        "room_walls": [[ [p[0], p[1]] for p in r.polygon ] for r in fp.rooms],
        "rooms": [
            {"id": r.id, "name": r.name, "polygon": [list(p) for p in r.polygon], "capacity": r.capacity}
            for r in fp.rooms
        ],
        "doors": [
            {"id": d.id, "rooms": list(d.rooms), "x": d.x, "y": d.y, "angle": d.angle, "width": d.width}
            for d in fp.doors
        ],
    }


@app.get("/api/curator")
def curator():
    from app.curator.rules import advice, room_ascii_graph

    status = _sim.status()
    level = load_level(_sim.level_id)
    level = {**level, "id": _sim.level_id}
    lines = advice(_sim.level_id, level, status)
    graph = room_ascii_graph(level, status)
    return {
        "level": _sim.level_id,
        "lines": [{"severity": l.severity, "text": l.text} for l in lines],
        "graph": graph,
    }


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()

    async def sender():
        global _last_step
        while True:
            # Multiple tabs share one sim: only the first sender past the DT
            # horizon advances physics, everyone else streams the latest frame.
            now = time.monotonic()
            if now - _last_step >= DT:
                _sim.update(DT)
                _last_step = now
            await ws.send_bytes(_sim.frame())
            if _sim.split:
                await ws.send_bytes(_sim.frame(side_b=True))
            await asyncio.sleep(DT)

    async def receiver():
        while True:
            msg = await ws.receive_json()
            mtype = msg.get("type")
            if mtype == "level":
                try:
                    _sim.reload(str(msg["id"]))
                    await ws.send_json({"type": "level", "ok": True, **_sim.status()})
                except FileNotFoundError:
                    await ws.send_json({"type": "level", "ok": False, "error": f"unknown level {msg.get('id')}"})
            elif mtype == "params":
                await ws.send_json({"type": "params", "ok": True, **_sim.apply_params(msg)})
            elif mtype == "split":
                _sim.set_split(bool(msg.get("on", True)))
                await ws.send_json({"type": "split", "ok": True, **_sim.status()})
            else:
                await ws.send_json({"type": "ack", "received": msg})

    send_task = asyncio.create_task(sender())
    try:
        await receiver()
    except WebSocketDisconnect:
        pass
    finally:
        send_task.cancel()


if os.path.isdir(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


@app.get("/")
def index():
    if os.path.isfile(os.path.join(STATIC_DIR, "index.html")):
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))
    return JSONResponse({"app": "CROWD GHOST", "hint": "frontend not built yet; see /ws and /api/health"})
