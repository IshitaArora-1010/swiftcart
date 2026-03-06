from uuid import UUID
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import crud, schemas
from app.database import get_db
from app.models import OrderStatus

router = APIRouter(
    prefix="/orders",
    tags=["Orders"],
)


@router.post("/", response_model=schemas.OrderResponse, status_code=status.HTTP_201_CREATED)
def create_order(order: schemas.OrderCreate, db: Session = Depends(get_db)):
    """
    Create a new order with one or more items.
    - total_amount is auto-calculated from item prices
    - Order starts in PENDING status
    - Auto-promoted to PROCESSING by background scheduler once fully paid
    """
    return crud.create_order(db, order)


@router.get("/", response_model=List[schemas.OrderListResponse])
def list_orders(status: Optional[OrderStatus] = None, db: Session = Depends(get_db)):
    """
    List all orders, sorted newest first.
    Optionally filter by status.
    """
    return crud.get_orders(db, status)


# IMPORTANT: specific sub-routes must come BEFORE the /{order_id} catch-all

@router.patch("/{order_id}/status", response_model=schemas.OrderResponse)
def update_order_status(
    order_id: UUID,
    status_update: schemas.OrderStatusUpdate,
    db: Session = Depends(get_db)
):
    """Manually update an order's status."""
    order = crud.update_order_status(db, order_id, status_update.status)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order with ID {order_id} not found"
        )
    return order


@router.post("/{order_id}/payments", response_model=schemas.PaymentResponse, status_code=status.HTTP_201_CREATED)
def make_payment(order_id: UUID, payment: schemas.PaymentCreate, db: Session = Depends(get_db)):
    """
    Record a (partial) payment against a PENDING order.
    The background scheduler promotes the order to PROCESSING once fully paid.
    """
    try:
        return crud.create_payment(db, order_id, payment)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{order_id}/payments", response_model=List[schemas.PaymentResponse])
def list_payments(order_id: UUID, db: Session = Depends(get_db)):
    """List all payments for a specific order, sorted oldest first."""
    order = crud.get_order(db, order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order with ID {order_id} not found"
        )
    return crud.get_payments_for_order(db, order_id)


@router.delete("/{order_id}/cancel", response_model=schemas.OrderResponse)
def cancel_order(order_id: UUID, db: Session = Depends(get_db)):
    """Cancel an order. Only PENDING orders can be cancelled."""
    try:
        order = crud.cancel_order(db, order_id)
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order with ID {order_id} not found"
            )
        return order
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# Catch-all /{order_id} MUST be last
@router.get("/{order_id}", response_model=schemas.OrderResponse)
def get_order(order_id: UUID, db: Session = Depends(get_db)):
    """Get full details of a specific order by its UUID."""
    order = crud.get_order(db, order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order with ID {order_id} not found"
        )
    return order
