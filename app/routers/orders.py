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
    - Auto-promoted to PROCESSING by background scheduler after 5 minutes
    """
    return crud.create_order(db, order)


@router.get("/", response_model=List[schemas.OrderListResponse])
def list_orders(status: Optional[OrderStatus] = None, db: Session = Depends(get_db)):
    """
    List all orders, sorted newest first.
    Optionally filter by status: PENDING, PROCESSING, SHIPPED, DELIVERED,
    CANCELLED, RETURN_REQUESTED, REFUNDED.
    """
    return crud.get_orders(db, status)


@router.get("/{order_id}", response_model=schemas.OrderResponse)
def get_order(order_id: UUID, db: Session = Depends(get_db)):
    """
    Get full details of a specific order by its UUID, including all line items.
    Returns 404 if the order does not exist.
    """
    order = crud.get_order(db, order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order with ID {order_id} not found"
        )
    return order


@router.patch("/{order_id}/status", response_model=schemas.OrderResponse)
def update_order_status(
    order_id: UUID,
    status_update: schemas.OrderStatusUpdate,
    db: Session = Depends(get_db)
):
    """
    Manually update an order's status.
    Used by the admin panel for shipping/delivery updates
    and by customers to request returns on delivered orders.
    Returns 404 if the order does not exist.
    """
    order = crud.update_order_status(db, order_id, status_update.status)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order with ID {order_id} not found"
        )
    return order


@router.delete("/{order_id}/cancel", response_model=schemas.OrderResponse)
def cancel_order(order_id: UUID, db: Session = Depends(get_db)):
    """
    Cancel an order. Only PENDING orders can be cancelled —
    returns HTTP 400 if the order has already moved past PENDING.
    Returns 404 if the order does not exist.
    """
    try:
        order = crud.cancel_order(db, order_id)
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order with ID {order_id} not found"
            )
        return order
    except ValueError as e:
        # crud.cancel_order raises ValueError when status is not PENDING
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
