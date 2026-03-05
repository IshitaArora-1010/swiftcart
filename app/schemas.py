from uuid import UUID
from datetime import datetime
from typing import List
from pydantic import BaseModel, field_validator
from app.models import OrderStatus


# ── Request schemas (incoming data) ──────────────────────────────────────────

class OrderItemCreate(BaseModel):
    """A single item in a new order request. Quantity and price must be positive."""
    product_name: str
    quantity: int
    unit_price: float

    @field_validator("quantity")
    @classmethod
    def quantity_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError("Quantity must be greater than 0")
        return v

    @field_validator("unit_price")
    @classmethod
    def price_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError("Unit price must be greater than 0")
        return v


class OrderCreate(BaseModel):
    """Payload for creating a new order. Must include at least one item."""
    customer_name: str
    customer_email: str
    items: List[OrderItemCreate]

    @field_validator("items")
    @classmethod
    def items_must_not_be_empty(cls, v):
        if not v:
            raise ValueError("Order must contain at least one item")
        return v


class OrderStatusUpdate(BaseModel):
    """Payload for manually updating an order's status (used by admin panel)."""
    status: OrderStatus


# ── Response schemas (outgoing data) ─────────────────────────────────────────

class OrderItemResponse(BaseModel):
    """Full representation of an order item returned in API responses."""
    id: UUID
    product_name: str
    quantity: int
    unit_price: float
    model_config = {"from_attributes": True}  # Allows mapping from SQLAlchemy ORM objects


class OrderResponse(BaseModel):
    """
    Full order detail response including all line items.
    Returned by GET /orders/{id}, POST /orders/, and status update endpoints.
    """
    id: UUID
    customer_name: str
    customer_email: str
    status: OrderStatus
    total_amount: float
    created_at: datetime
    updated_at: datetime
    items: List[OrderItemResponse]
    model_config = {"from_attributes": True}


class OrderListResponse(BaseModel):
    """
    Lightweight order summary for list views (no items included).
    Returned by GET /orders/ to keep response payloads small.
    """
    id: UUID
    customer_name: str
    customer_email: str
    status: OrderStatus
    total_amount: float
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
