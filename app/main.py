import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router
from app.db import close_pool
from app.logger import configure_logging
from app.scheduler import start_scheduler, stop_scheduler

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()
    await close_pool()


app = FastAPI(
    title="Divergence Alert Microservice",
    description="Event A vs Market B divergence alerts via Telegram",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(api_router, prefix="/api", tags=["api"])

static_dir = Path(__file__).resolve().parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/")
    async def index():
        return FileResponse(static_dir / "index.html")
else:

    @app.get("/")
    async def root():
        return {"service": "divergence-alerts", "docs": "/docs", "health": "/api/health"}
