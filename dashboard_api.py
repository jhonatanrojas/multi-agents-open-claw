#!/usr/bin/env python3
"""
dashboard_api.py - SSE + REST API for the Dev Squad Dashboard
-------------------------------------------------------------
Serves:
  GET  /api/state          -> current shared memory snapshot
  GET  /api/stream         -> SSE stream of state changes (polls every 2s)
  GET  /api/agents/world   -> proxies Miniverse /api/agents
  POST /api/project/start  -> triggers orchestrator with a project brief
"""

import json
import asyncio
import sys
import subprocess
from pathlib import Path
from datetime import datetime

import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

from shared_state import load_memory
MINIVERSE_URL = "https://miniverse-public-production.up.railway.app"

app = FastAPI(title="Dev Squad Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/state")
def get_state():
    return load_memory()


@app.get("/api/stream")
async def stream_state():
    """Server-Sent Events stream — pushes state every 2 seconds."""
    async def generator():
        last = None
        while True:
            current = json.dumps(load_memory(), sort_keys=True)
            if current != last:
                last = current
                yield f"data: {current}\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(generator(), media_type="text/event-stream")


@app.get("/api/agents/world")
def agents_in_world():
    """Proxy Miniverse agent list."""
    try:
        r = requests.get(f"{MINIVERSE_URL}/api/agents", timeout=5)
        return r.json()
    except Exception as e:
        return {"error": str(e), "agents": []}


class ProjectRequest(BaseModel):
    brief: str
    repo_url: str | None = None
    repo_name: str | None = None
    branch: str | None = None
    allow_init_repo: bool = False


@app.post("/api/project/start")
async def start_project(req: ProjectRequest):
    """Spawn orchestrator in background."""
    args = [sys.executable, "orchestrator.py"]
    if req.repo_url:
        args.extend(["--repo-url", req.repo_url])
    if req.repo_name:
        args.extend(["--repo-name", req.repo_name])
    if req.branch:
        args.extend(["--branch", req.branch])
    if req.allow_init_repo:
        args.append("--allow-init-repo")
    args.append(req.brief)

    log_path = Path("logs/orchestrator.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log_file:
        subprocess.Popen(
            args,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
    return {"status": "started", "brief": req.brief, "ts": datetime.utcnow().isoformat()}


@app.get("/api/logs")
def get_logs():
    mem = load_memory()
    return {"log": mem.get("log", [])[-100:]}  # last 100 entries
