from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.routers import dashboard, organizations, scans
from app.scheduler import create_scheduler

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

_scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    global _scheduler
    if os.environ.get("GEO_DASHBOARD_DISABLE_SCHEDULER") != "1":
        _scheduler = create_scheduler()
        _scheduler.start()
    yield
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)


app = FastAPI(title="GEO Scan Dashboard", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.include_router(dashboard.router)
app.include_router(organizations.router)
app.include_router(scans.router)


@app.get("/")
def root():
    return RedirectResponse(url="/dashboard")
