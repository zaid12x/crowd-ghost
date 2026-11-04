# CROWD GHOST — all-in-one: frontend build -> FastAPI serves app + API.
# Build:  docker build -t crowd-ghost .
# Run:    docker run --rm -p 8000:8000 crowd-ghost
# Choose hall:  docker run --rm -e CROWD_GHOST_LEVEL=rush -p 8000:8000 crowd-ghost

# --- stage 1: frontend build ---
FROM node:20-slim AS fe
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN cd frontend && npm ci
COPY frontend/ ./frontend/
RUN cd frontend && npm run build

# --- stage 2: runtime ---
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    CROWD_GHOST_LEVEL=bottleneck
WORKDIR /app

COPY backend/requirements-runtime.txt ./backend/requirements-runtime.txt
RUN pip install --no-cache-dir -r ./backend/requirements-runtime.txt

COPY backend/ ./backend/
COPY results/optimizer.json ./results/optimizer.json
COPY --from=fe /build/frontend/dist ./backend/app/static

EXPOSE 8000
# Optimizer is baked in; without it the split pane falls back to level defaults.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
