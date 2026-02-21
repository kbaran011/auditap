"""FastAPI application entry point."""
import logging
import logging.config
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse

from app.api.routes import router
from app.database import init_db
from app.config import settings
from app.middleware.rate_limit import RateLimitMiddleware

# Configure structured logging at startup
logging.config.dictConfig({
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            "datefmt": "%Y-%m-%dT%H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
        },
    },
    "root": {
        "level": "INFO",
        "handlers": ["console"],
    },
})

logger = logging.getLogger(__name__)
templates_dir = Path(__file__).parent / "templates"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("A/P Anomaly Detector starting up — initializing database tables")
    try:
        init_db()
        logger.info("Database ready")
    except Exception as e:
        # Don't block startup: server must bind so /health passes (e.g. Railway healthcheck)
        logger.warning("Database init failed (server will start anyway): %s", e)
    yield
    logger.info("A/P Anomaly Detector shutting down")


app = FastAPI(
    title="A/P Anomaly Detector",
    description="Read-only audit layer for accounts payable — find duplicate invoices, price creep, and leaks.",
    version="0.2.0",
    lifespan=lifespan,
)

# Rate limiting: IP-based and user-based (X-API-Key) to prevent abuse (OWASP API4:2019)
app.add_middleware(
    RateLimitMiddleware,
    requests_per_minute_ip=settings.rate_limit_requests_per_minute_ip,
    requests_per_minute_user=settings.rate_limit_requests_per_minute_user,
    exempt_paths=["/health", "/"],
)

app.include_router(router, prefix="/api", tags=["api"])

templates = Jinja2Templates(directory=str(templates_dir))


@app.get("/")
def landing(request: Request):
    """Marketing landing page."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/app")
def dashboard(request: Request):
    """App dashboard."""
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/health")
def health():
    return {"status": "ok"}
