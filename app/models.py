import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Integer, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import enum

from app.database import Base


class OrderStatus(str, enum.Enum):
    """All possible states an order can be in throughout its lifecycle."""
    PENDING = "PENDING"                    # Order placed, not yet picked up
    PROCESSING = "PROCESSING"              # Auto-promoted from PENDING after 5 minutes
    SHIPPED = "SHIPPED"                    # Dispatched by warehouse
    DELIVERED = "DELIVERED"               # Received by customer
    CANCELLED = "CANCELLED"               # Cancelled (only allowed from PENDING)
    RETURN_REQUESTED = "RETURN_REQUESTED" # Customer requested a return
    REFUNDED = "REFUNDED"                 # Refund issued after return approved


class Order(Base):
    """
    Represents a customer order.
    One order can have multiple items (see OrderItem).
    total_amount is calculated at creation time from item prices.
    """
    __tablename__ = "orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    customer_name = Column(String, nullable=False)
    customer_email = Column(String, nullable=False)
    status = Column(
        SAEnum(OrderStatus, name="orderstatus"),
        default=OrderStatus.PENDING,
        nullable=False
    )
    total_amount = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    # One-to-many: an order has many items
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    """
    A single line item within an order.
    Stores a snapshot of the product name and price at the time of purchase.
    """
    __tablename__ = "order_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False)
    product_name = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)  # Price at time of purchase

    # Many-to-one: each item belongs to one order
    order = relationship("Order", back_populates="items")
