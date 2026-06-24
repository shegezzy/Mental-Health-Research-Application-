import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from backend.config.settings import settings
from backend.routes.api import router
from backend.services.sheets import ensure_headers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Mental Health Research API")
    try:
        ensure_headers()
    except Exception as e:
        logger.warning(f"Sheet header check skipped: {e}")
    yield
    logger.info("Shutting down")


app = FastAPI(
    title="Mental Health Research API",
    description=(
        "Academic research tool for AI-assisted analysis of social media behaviour "
        "and mental health indicators. NOT a diagnostic tool."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")

# Serve frontend static files
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_index():
        return FileResponse(os.path.join(frontend_dir, "index.html"))

@app.get("/health")
async def health():
    return {"status": "ok", "service": "mental-health-research-api"}
