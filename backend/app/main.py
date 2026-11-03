"""FastAPI app: HTTP + WebSocket endpoint (binary frames at 30 Hz)."""

import asyncio
import json
import os
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.sim_loop import TICK_HZ, DT, SimState, LEVELS_DIR, load_level

app = FastAPI(title="CROWD GHOST", version="0.1.0")

_sim = SimState()

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


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()

    async def sender():
        while True:
            _sim.update(DT)
            await ws.send_bytes(_sim.frame())
            await asyncio.sleep(DT)

    async def receiver():
        while True:
            msg = await ws.receive_json()
            if msg.get("type") == "level":
                try:
                    _sim.reload(str(msg["id"]))
                    await ws.send_json({"type": "level", "ok": True, **_sim.status()})
                except FileNotFoundError:
                    await ws.send_json({"type": "level", "ok": False, "error": f"unknown level {msg.get('id')}"})
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
