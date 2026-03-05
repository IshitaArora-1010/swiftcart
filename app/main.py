import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.database import engine, Base
from app.routers import orders, chat
from app.scheduler import start_scheduler

# Configure structured logging for the entire application
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Resolve the project root directory so we can serve index.html and admin.html
BASE_DIR = os.path.dirname(os.path.dirname(__file__))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler (runs on startup and shutdown).
    - Startup: creates all DB tables if they don't exist, starts the background scheduler
    - Shutdown: gracefully stops the scheduler to avoid orphaned threads
    """
    logger.info("Starting up SwiftCart Order Processing System...")
    Base.metadata.create_all(bind=engine)  # Create tables (idempotent — safe to run on every start)
    scheduler = start_scheduler()
    yield
    logger.info("Shutting down...")
    scheduler.shutdown()


app = FastAPI(
    title="SwiftCart — Order Processing API",
    version="1.0.0",
    description="REST API for managing e-commerce orders with background auto-processing.",
    lifespan=lifespan,
)

# Allow all origins so the frontend (served from the same host) and admin panel can call the API.
# In production this should be restricted to the actual domain.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers
app.include_router(orders.router)  # /orders/*
app.include_router(chat.router)    # /chat/


@app.get("/", include_in_schema=False)
def serve_frontend():
    """Serve the customer-facing storefront (index.html) at the root URL."""
    path = os.path.join(BASE_DIR, "index.html")
    return FileResponse(path) if os.path.exists(path) else {"status": "ok"}


@app.get("/admin", include_in_schema=False)
def serve_admin():
    """Serve the admin dashboard (admin.html) at /admin."""
    path = os.path.join(BASE_DIR, "admin.html")
    return FileResponse(path) if os.path.exists(path) else {"error": "admin.html not found"}


@app.get("/health", tags=["Health"])
def health_check():
    """Simple health check endpoint — useful for Docker health checks and monitoring."""
    return {"status": "healthy"}
