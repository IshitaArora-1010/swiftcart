from uuid import UUID
from typing import List, Optional
from sqlalchemy.orm import Session

from app import models, schemas
from app.models import OrderStatus


def create_order(db: Session, order_data: schemas.OrderCreate) -> models.Order:
    """
    Create a new order with one or more items.
    Calculates total_amount by summing (quantity × unit_price) for each item.
    The order starts in PENDING status. It will only be promoted to PROCESSING
    by the background scheduler once payments cover the full total_amount.
    """
    total_amount = sum(item.quantity * item.unit_price for item in order_data.items)

    db_order = models.Order(
        customer_name=order_data.customer_name,
        customer_email=order_data.customer_email,
        total_amount=total_amount,
        status=OrderStatus.PENDING,
    )
    db.add(db_order)
    db.flush()  # Flush to get the auto-generated order ID before inserting items

    for item in order_data.items:
        db_item = models.OrderItem(
            order_id=db_order.id,
            product_name=item.product_name,
            quantity=item.quantity,
            unit_price=item.unit_price,
        )
        db.add(db_item)

    db.commit()
    db.refresh(db_order)
    return db_order


def get_order(db: Session, order_id: UUID) -> Optional[models.Order]:
    """Fetch a single order by its UUID. Returns None if not found."""
    return db.query(models.Order).filter(models.Order.id == order_id).first()


def get_orders(db: Session, status: Optional[OrderStatus] = None) -> List[models.Order]:
    """
    Fetch all orders, sorted newest first.
    Optionally filter by status — if None, returns all orders regardless of status.
    """
    query = db.query(models.Order)
    if status:
        query = query.filter(models.Order.status == status)
    return query.order_by(models.Order.created_at.desc()).all()


def update_order_status(db: Session, order_id: UUID, new_status: OrderStatus) -> Optional[models.Order]:
    """
    Update the status of an order to any valid OrderStatus value.
    Used by the admin panel and the customer return/cancel flow.
    Returns None if the order does not exist.
    """
    db_order = get_order(db, order_id)
    if not db_order:
        return None

    db_order.status = new_status
    db.commit()
    db.refresh(db_order)
    return db_order


def cancel_order(db: Session, order_id: UUID) -> Optional[models.Order]:
    """
    Cancel an order. Only orders in PENDING status can be cancelled —
    once processing has started it is too late to cancel.
    Raises ValueError if the order is not in PENDING status.
    Returns None if the order does not exist.
    """
    db_order = get_order(db, order_id)
    if not db_order:
        return None

    if db_order.status != OrderStatus.PENDING:
        raise ValueError(
            f"Cannot cancel order with status '{db_order.status}'. Only PENDING orders can be cancelled."
        )

    db_order.status = OrderStatus.CANCELLED
    db.commit()
    db.refresh(db_order)
    return db_order


def create_payment(db: Session, order_id: UUID, payment_data: schemas.PaymentCreate) -> models.Payment:
    """
    Record a payment against an order.

    Rules enforced:
    - Order must exist (raises ValueError if not)
    - Order must be in PENDING status — cannot pay for cancelled or already-processing orders
    - Payment cannot exceed the remaining balance (prevents overpayment)

    After payment is recorded, the caller should let the background scheduler
    handle the PENDING → PROCESSING transition on its next run.
    """
    db_order = get_order(db, order_id)
    if not db_order:
        raise ValueError(f"Order with ID {order_id} not found")

    if db_order.status != OrderStatus.PENDING:
        raise ValueError(
            f"Cannot make a payment for an order with status '{db_order.status}'. "
            "Payments are only accepted for PENDING orders."
        )

    # Prevent overpayment — payment must not exceed the outstanding balance
    remaining = db_order.remaining_amount
    if payment_data.amount > remaining:
        raise ValueError(
            f"Payment of {payment_data.amount} exceeds the remaining balance of {remaining}. "
            "You cannot overpay an order."
        )

    db_payment = models.Payment(
        order_id=order_id,
        amount=payment_data.amount,
    )
    db.add(db_payment)
    db.commit()
    db.refresh(db_payment)
    return db_payment


def get_payments_for_order(db: Session, order_id: UUID) -> List[models.Payment]:
    """
    Fetch all payments made against a specific order, sorted oldest first.
    Returns an empty list if the order has no payments yet.
    """
    return (
        db.query(models.Payment)
        .filter(models.Payment.order_id == order_id)
        .order_by(models.Payment.created_at.asc())
        .all()
    )


def promote_pending_orders(db: Session) -> int:
    """
    Background job function: promotes fully paid PENDING orders to PROCESSING.

    An order is eligible for promotion only when:
        sum of all its payments >= total_amount

    Orders that are still partially paid remain in PENDING until the
    customer completes their payment.

    Returns the number of orders promoted.
    """
    pending_orders = db.query(models.Order).filter(
        models.Order.status == OrderStatus.PENDING
    ).all()

    count = 0
    for order in pending_orders:
        # Use the computed property from the model to check payment completion
        if order.paid_amount >= order.total_amount:
            order.status = OrderStatus.PROCESSING
            count += 1

    db.commit()
    return count
