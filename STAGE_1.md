# Stage 1 — Skeleton

**Built**
- `backend/app/protocol.py` — binary frame codec (`CGF1` header + float32 agent/room arrays).
- `backend/app/sim_loop.py` — dummy random-walk agents @ 30 Hz (Stage 3 swaps in social-force physics; protocol unchanged).
- `backend/app/main.py` — FastAPI: `/ws` (binary frames, 30 Hz), `/api/health`, static hosting of the built frontend.
- `frontend/` — Vite + TypeScript + Three.js; WebSocket binary decoder (`src/net/ws.ts`); orthographic top-down view, `InstancedMesh` dots.
- `backend/build_frontend.ps1` — build + copy `frontend/dist` → `backend/app/static`.

**Gate: dots move in the browser from server data; pytest green — PASS**

- pytest: `2 passed` (`python -m pytest tests -q`).
- Verified live at http://127.0.0.1:8000/ — server streams TICK incrementing, AGENTS 60; dots rendered from WS frame data (instanceMatrix version bumps each frame).
- Frontend builds clean: `tsc && vite build`.

**Bugs fixed along the way (honest log)**
1. Orthographic camera bounds are in *view* space; `OrthographicCamera(0, W, H, 0)` at position `(W/2, H/2, 50)` rendered only a bottom-left quarter. Fix: symmetric frustum centered on the look axis.
2. `InstancedMesh` was frustum-culled against stale bounds; with dynamic instance matrices agents vanished. Fix: `frustumCulled = false`.
3. Embedded browser can resize the canvas buffer without firing `resize`; render loop now self-heals viewport to match `clientWidth/Height × DPR` (canvas CSS is `100vw/100vh`).

**Reproduce**
```
cd backend && python -m pytest tests -q
python -m uvicorn app.main:app --port 8000
```
Open http://127.0.0.1:8000/ (frontend prebuilt via `build_frontend.ps1`).

**Not done (by design)**
- Real crowd model arrives in Stage 3; frame format already carries per-room stats (unused, 0 rooms).
