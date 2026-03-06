from uuid import UUID
from datetime import datetime
from typing import List
from pydantic import BaseModel, field_validator
from app.models import OrderStatus


# ── Payment schemas ───────────────────────────────────────────────────────────

class PaymentCreate(BaseModel):
    """Payload for making a payment towards an order. Amount must be positive."""
    amount: float

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError("Payment amount must be greater than 0")
        return v


class PaymentResponse(BaseModel):
    """Represents a single payment record returned in API responses."""
    id: UUID
    order_id: UUID
    amount: float
    created_at: datetime
    model_config = {"from_attributes": True}


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
    model_config = {"from_attributes": True}


class OrderResponse(BaseModel):
    """
    Full order detail response including line items and payment summary.
    paid_amount and remaining_amount are computed from the payments relationship.
    """
    id: UUID
    customer_name: str
    customer_email: str
    status: OrderStatus
    total_amount: float
    paid_amount: float        # Sum of all payments made so far
    remaining_amount: float   # total_amount - paid_amount
    created_at: datetime
    updated_at: datetime
    items: List[OrderItemResponse]
    payments: List[PaymentResponse]
    model_config = {"from_attributes": True}


class OrderListResponse(BaseModel):
    """
    Lightweight order summary for list views.
    Includes payment status so customers can see outstanding balance at a glance.
    """
    id: UUID
    customer_name: str
    customer_email: str
    status: OrderStatus
    total_amount: float
    paid_amount: float
    remaining_amount: float
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
