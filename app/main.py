import logging
import os
from uuid import UUID
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import engine, Base, get_db
from app.routers import orders, chat
from app.scheduler import start_scheduler
from app import crud, schemas

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(__file__))


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up SwiftCart Order Processing System...")
    Base.metadata.create_all(bind=engine)
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register chat router
app.include_router(chat.router)


# ── Orders routes registered DIRECTLY here to guarantee correct order ──────────

@app.post("/orders/", response_model=schemas.OrderResponse, status_code=201, tags=["Orders"])
def create_order(order: schemas.OrderCreate, db: Session = Depends(get_db)):
    return crud.create_order(db, order)


@app.get("/orders/", response_model=List[schemas.OrderListResponse], tags=["Orders"])
def list_orders(status: Optional[schemas.OrderStatus] = None, db: Session = Depends(get_db)):
    return crud.get_orders(db, status)


@app.patch("/orders/{order_id}/status", response_model=schemas.OrderResponse, tags=["Orders"])
def update_order_status(order_id: UUID, status_update: schemas.OrderStatusUpdate, db: Session = Depends(get_db)):
    order = crud.update_order_status(db, order_id, status_update.status)
    if not order:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    return order


@app.post("/orders/{order_id}/payments", response_model=schemas.PaymentResponse, status_code=201, tags=["Orders"])
def make_payment(order_id: UUID, payment: schemas.PaymentCreate, db: Session = Depends(get_db)):
    try:
        return crud.create_payment(db, order_id, payment)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders/{order_id}/payments", response_model=List[schemas.PaymentResponse], tags=["Orders"])
def list_payments(order_id: UUID, db: Session = Depends(get_db)):
    order = crud.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    return crud.get_payments_for_order(db, order_id)


@app.delete("/orders/{order_id}/cancel", response_model=schemas.OrderResponse, tags=["Orders"])
def cancel_order(order_id: UUID, db: Session = Depends(get_db)):
    try:
        order = crud.cancel_order(db, order_id)
        if not order:
            raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
        return order
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders/{order_id}", response_model=schemas.OrderResponse, tags=["Orders"])
def get_order(order_id: UUID, db: Session = Depends(get_db)):
    order = crud.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    return order


# ── Static pages ───────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
def serve_frontend():
    path = os.path.join(BASE_DIR, "index.html")
    return FileResponse(path) if os.path.exists(path) else {"status": "ok"}


@app.get("/admin", include_in_schema=False)
def serve_admin():
    path = os.path.join(BASE_DIR, "admin.html")
    return FileResponse(path) if os.path.exists(path) else {"error": "admin.html not found"}


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "healthy"}
