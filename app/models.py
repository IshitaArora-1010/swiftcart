import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Integer, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import enum

from app.database import Base


class OrderStatus(str, enum.Enum):
    """All possible states an order can be in throughout its lifecycle."""
    PENDING = "PENDING"                    # Order placed, awaiting full payment
    PROCESSING = "PROCESSING"              # Fully paid — promoted by background scheduler
    SHIPPED = "SHIPPED"                    # Dispatched by warehouse
    DELIVERED = "DELIVERED"               # Received by customer
    CANCELLED = "CANCELLED"               # Cancelled (only allowed from PENDING)
    RETURN_REQUESTED = "RETURN_REQUESTED" # Customer requested a return
    REFUNDED = "REFUNDED"                 # Refund issued after return approved


class Order(Base):
    """
    Represents a customer order.
    Orders start in PENDING and are only promoted to PROCESSING by the
    background scheduler once the total payments equal the total_amount.
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

    # One-to-many: an order can have multiple partial payments
    payments = relationship("Payment", back_populates="order", cascade="all, delete-orphan")

    @property
    def paid_amount(self) -> float:
        """Sum of all payments made against this order so far."""
        return round(sum(p.amount for p in self.payments), 2)

    @property
    def remaining_amount(self) -> float:
        """Amount still outstanding before the order can be processed."""
        return round(self.total_amount - self.paid_amount, 2)


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


class Payment(Base):
    """
    Represents a single payment made towards an order.
    Customers can make multiple partial payments — the order moves to
    PROCESSING only when the sum of all payments equals the total_amount.
    """
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False)
    amount = Column(Float, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Many-to-one: each payment belongs to one order
    order = relationship("Order", back_populates="payments")
