"""FastAPI app: HTTP + WebSocket endpoint (binary frames at 30 Hz)."""

import asyncio
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.sim_loop import TICK_HZ, DT, SimState

app = FastAPI(title="CROWD GHOST", version="0.1.0")

_sim = SimState()

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


@app.get("/api/health")
def health():
    return {"ok": True, "tick": _sim.tick, "agents": len(_sim.agents)}


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
            # Stage 7 will hot-reload params here; Stage 1 only acknowledges.
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
