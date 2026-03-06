import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import patch

from app.main import app
from app.database import Base, get_db
from app import crud

# StaticPool forces all connections to share the same in-memory database.
# Without it, each connection gets its own isolated DB and tables vanish between calls.
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """Replace the real DB session with the test SQLite session for all tests."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_db():
    """Create all tables before each test, drop them after. Ensures test isolation."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


client = TestClient(app)


# ── Helpers ───────────────────────────────────────────────────────────────────

def create_sample_order(customer_name="John Doe", customer_email="john@example.com"):
    """Helper to create a standard two-item order with total_amount = 1049.99."""
    return client.post("/orders/", json={
        "customer_name": customer_name,
        "customer_email": customer_email,
        "items": [
            {"product_name": "Laptop", "quantity": 1, "unit_price": 999.99},
            {"product_name": "Mouse", "quantity": 2, "unit_price": 25.00},
        ]
    })


def advance_order_to(order_id: str, target_status: str):
    """Helper to move an order to a given status in one call."""
    return client.patch(f"/orders/{order_id}/status", json={"status": target_status})


def pay(order_id: str, amount: float):
    """Helper to make a payment against an order."""
    return client.post(f"/orders/{order_id}/payments", json={"amount": amount})


# ── Create Order ──────────────────────────────────────────────────────────────

def test_create_order_success():
    """A valid order should be created with PENDING status, zero paid, full remaining."""
    response = create_sample_order()
    assert response.status_code == 201
    data = response.json()
    assert data["customer_name"] == "John Doe"
    assert data["status"] == "PENDING"
    assert data["total_amount"] == pytest.approx(1049.99)
    assert data["paid_amount"] == 0.0
    assert data["remaining_amount"] == pytest.approx(1049.99)
    assert len(data["items"]) == 2
    assert data["payments"] == []


def test_create_order_total_amount_calculated_correctly():
    """total_amount = sum of quantity × unit_price across all items."""
    response = client.post("/orders/", json={
        "customer_name": "Test",
        "customer_email": "test@example.com",
        "items": [
            {"product_name": "Item A", "quantity": 3, "unit_price": 100.00},
            {"product_name": "Item B", "quantity": 2, "unit_price": 50.00},
        ]
    })
    assert response.status_code == 201
    assert response.json()["total_amount"] == pytest.approx(400.00)


def test_create_order_empty_items():
    response = client.post("/orders/", json={
        "customer_name": "Jane", "customer_email": "jane@example.com", "items": []
    })
    assert response.status_code == 422


def test_create_order_invalid_quantity():
    response = client.post("/orders/", json={
        "customer_name": "Jane", "customer_email": "jane@example.com",
        "items": [{"product_name": "Book", "quantity": 0, "unit_price": 10.0}]
    })
    assert response.status_code == 422


def test_create_order_negative_quantity():
    response = client.post("/orders/", json={
        "customer_name": "Jane", "customer_email": "jane@example.com",
        "items": [{"product_name": "Book", "quantity": -1, "unit_price": 10.0}]
    })
    assert response.status_code == 422


def test_create_order_invalid_price():
    response = client.post("/orders/", json={
        "customer_name": "Jane", "customer_email": "jane@example.com",
        "items": [{"product_name": "Book", "quantity": 1, "unit_price": -5.0}]
    })
    assert response.status_code == 422


def test_create_order_zero_price():
    response = client.post("/orders/", json={
        "customer_name": "Jane", "customer_email": "jane@example.com",
        "items": [{"product_name": "Book", "quantity": 1, "unit_price": 0}]
    })
    assert response.status_code == 422


# ── Payments ──────────────────────────────────────────────────────────────────

def test_single_full_payment():
    """One payment covering the full amount should set remaining to 0."""
    order_id = create_sample_order().json()["id"]
    response = pay(order_id, 1049.99)
    assert response.status_code == 201
    assert response.json()["amount"] == pytest.approx(1049.99)

    order = client.get(f"/orders/{order_id}").json()
    assert order["paid_amount"] == pytest.approx(1049.99)
    assert order["remaining_amount"] == pytest.approx(0.0)


def test_multiple_partial_payments():
    """Three partial payments should accumulate and reduce remaining correctly."""
    order_id = create_sample_order().json()["id"]  # total = 1049.99

    pay(order_id, 500.00)
    pay(order_id, 300.00)
    pay(order_id, 249.99)

    order = client.get(f"/orders/{order_id}").json()
    assert order["paid_amount"] == pytest.approx(1049.99)
    assert order["remaining_amount"] == pytest.approx(0.0)
    assert len(order["payments"]) == 3


def test_partial_payment_updates_remaining():
    """A partial payment should reduce remaining_amount but not clear it."""
    order_id = create_sample_order().json()["id"]  # total = 1049.99
    pay(order_id, 400.00)

    order = client.get(f"/orders/{order_id}").json()
    assert order["paid_amount"] == pytest.approx(400.00)
    assert order["remaining_amount"] == pytest.approx(649.99)
    assert order["status"] == "PENDING"  # Not yet fully paid


def test_payment_zero_amount_rejected():
    """A zero payment should be rejected with 422."""
    order_id = create_sample_order().json()["id"]
    response = pay(order_id, 0)
    assert response.status_code == 422


def test_payment_negative_amount_rejected():
    """A negative payment should be rejected with 422."""
    order_id = create_sample_order().json()["id"]
    response = pay(order_id, -100)
    assert response.status_code == 422


def test_payment_exceeds_remaining_rejected():
    """Payment that exceeds remaining balance should be rejected with 400."""
    order_id = create_sample_order().json()["id"]  # total = 1049.99
    response = pay(order_id, 2000.00)
    assert response.status_code == 400
    assert "remaining balance" in response.json()["detail"].lower()


def test_payment_exactly_remaining_accepted():
    """Paying exactly the remaining balance should succeed."""
    order_id = create_sample_order().json()["id"]
    pay(order_id, 1000.00)
    response = pay(order_id, 49.99)  # exact remaining
    assert response.status_code == 201


def test_payment_on_cancelled_order_rejected():
    """Cannot make a payment on a cancelled order."""
    order_id = create_sample_order().json()["id"]
    client.delete(f"/orders/{order_id}/cancel")
    response = pay(order_id, 100.00)
    assert response.status_code == 400
    assert "PENDING" in response.json()["detail"]


def test_payment_on_processing_order_rejected():
    """Cannot make a payment once the order is already being processed."""
    order_id = create_sample_order().json()["id"]
    advance_order_to(order_id, "PROCESSING")
    response = pay(order_id, 100.00)
    assert response.status_code == 400


def test_payment_order_not_found():
    """Payment on a non-existent order should return 400."""
    response = pay("00000000-0000-0000-0000-000000000000", 100.00)
    assert response.status_code == 400


def test_list_payments_for_order():
    """GET /orders/{id}/payments should return all payments in chronological order."""
    order_id = create_sample_order().json()["id"]
    pay(order_id, 300.00)
    pay(order_id, 400.00)

    response = client.get(f"/orders/{order_id}/payments")
    assert response.status_code == 200
    payments = response.json()
    assert len(payments) == 2
    assert payments[0]["amount"] == pytest.approx(300.00)
    assert payments[1]["amount"] == pytest.approx(400.00)


def test_list_payments_order_not_found():
    """Listing payments for a non-existent order should return 404."""
    response = client.get("/orders/00000000-0000-0000-0000-000000000000/payments")
    assert response.status_code == 404


def test_list_payments_empty():
    """A new order with no payments should return an empty list."""
    order_id = create_sample_order().json()["id"]
    response = client.get(f"/orders/{order_id}/payments")
    assert response.status_code == 200
    assert response.json() == []


# ── Scheduler — promote only fully paid orders ────────────────────────────────

def test_scheduler_does_not_promote_unpaid_order():
    """An order with no payments must stay PENDING after scheduler runs."""
    create_sample_order()

    db = TestingSessionLocal()
    try:
        count = crud.promote_pending_orders(db)
    finally:
        db.close()

    assert count == 0
    orders = client.get("/orders/?status=PENDING").json()
    assert len(orders) == 1


def test_scheduler_does_not_promote_partially_paid_order():
    """An order with partial payment must stay PENDING after scheduler runs."""
    order_id = create_sample_order().json()["id"]
    pay(order_id, 500.00)  # partial — total is 1049.99

    db = TestingSessionLocal()
    try:
        count = crud.promote_pending_orders(db)
    finally:
        db.close()

    assert count == 0
    order = client.get(f"/orders/{order_id}").json()
    assert order["status"] == "PENDING"


def test_scheduler_promotes_fully_paid_order():
    """An order fully paid must be promoted to PROCESSING by the scheduler."""
    order_id = create_sample_order().json()["id"]
    pay(order_id, 1049.99)  # full payment

    db = TestingSessionLocal()
    try:
        count = crud.promote_pending_orders(db)
    finally:
        db.close()

    assert count == 1
    order = client.get(f"/orders/{order_id}").json()
    assert order["status"] == "PROCESSING"


def test_scheduler_promotes_only_fully_paid_orders():
    """Only fully paid orders are promoted — partially paid ones stay PENDING."""
    order1_id = create_sample_order("Alice", "alice@example.com").json()["id"]
    order2_id = create_sample_order("Bob", "bob@example.com").json()["id"]

    pay(order1_id, 1049.99)   # fully paid
    pay(order2_id, 500.00)    # partially paid

    db = TestingSessionLocal()
    try:
        count = crud.promote_pending_orders(db)
    finally:
        db.close()

    assert count == 1
    assert client.get(f"/orders/{order1_id}").json()["status"] == "PROCESSING"
    assert client.get(f"/orders/{order2_id}").json()["status"] == "PENDING"


def test_scheduler_promotes_multiple_fully_paid_orders():
    """All fully paid orders should be promoted in a single scheduler run."""
    order1_id = create_sample_order("Alice", "alice@example.com").json()["id"]
    order2_id = create_sample_order("Bob", "bob@example.com").json()["id"]

    pay(order1_id, 1049.99)
    pay(order2_id, 1049.99)

    db = TestingSessionLocal()
    try:
        count = crud.promote_pending_orders(db)
    finally:
        db.close()

    assert count == 2


def test_scheduler_skips_non_pending_orders():
    """Scheduler should not touch orders that are not in PENDING status."""
    order_id = create_sample_order().json()["id"]
    advance_order_to(order_id, "SHIPPED")
    pay_response = client.post(f"/orders/{order_id}/payments", json={"amount": 1049.99})
    # payment rejected since not PENDING — that's expected

    db = TestingSessionLocal()
    try:
        count = crud.promote_pending_orders(db)
    finally:
        db.close()

    assert count == 0


def test_scheduler_no_pending_orders():
    """Scheduler should return 0 when there are no PENDING orders at all."""
    db = TestingSessionLocal()
    try:
        count = crud.promote_pending_orders(db)
    finally:
        db.close()
    assert count == 0


# ── Get / List Orders ─────────────────────────────────────────────────────────

def test_get_order_success():
    """Getting an order by ID should return full details including payments list."""
    created = create_sample_order().json()
    response = client.get(f"/orders/{created['id']}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == created["id"]
    assert len(data["items"]) == 2
    assert "paid_amount" in data
    assert "remaining_amount" in data
    assert "payments" in data


def test_get_order_not_found():
    response = client.get("/orders/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_list_orders_includes_payment_info():
    """List response should include paid_amount and remaining_amount per order."""
    order_id = create_sample_order().json()["id"]
    pay(order_id, 300.00)

    response = client.get("/orders/")
    assert response.status_code == 200
    order = response.json()[0]
    assert order["paid_amount"] == pytest.approx(300.00)
    assert order["remaining_amount"] == pytest.approx(749.99)


def test_list_orders_filter_by_status():
    create_sample_order()
    response = client.get("/orders/?status=PENDING")
    assert response.status_code == 200
    assert all(o["status"] == "PENDING" for o in response.json())


def test_list_orders_filter_no_results():
    create_sample_order()
    response = client.get("/orders/?status=DELIVERED")
    assert response.status_code == 200
    assert response.json() == []


# ── Update Status ─────────────────────────────────────────────────────────────

def test_update_order_status_to_processing():
    created = create_sample_order().json()
    response = advance_order_to(created["id"], "PROCESSING")
    assert response.status_code == 200
    assert response.json()["status"] == "PROCESSING"


def test_update_order_status_to_return_requested():
    order_id = create_sample_order().json()["id"]
    advance_order_to(order_id, "DELIVERED")
    response = advance_order_to(order_id, "RETURN_REQUESTED")
    assert response.status_code == 200
    assert response.json()["status"] == "RETURN_REQUESTED"


def test_update_order_status_to_refunded():
    order_id = create_sample_order().json()["id"]
    advance_order_to(order_id, "DELIVERED")
    advance_order_to(order_id, "RETURN_REQUESTED")
    response = advance_order_to(order_id, "REFUNDED")
    assert response.status_code == 200
    assert response.json()["status"] == "REFUNDED"


def test_update_order_status_not_found():
    response = client.patch(
        "/orders/00000000-0000-0000-0000-000000000000/status",
        json={"status": "SHIPPED"}
    )
    assert response.status_code == 404


def test_update_order_invalid_status():
    created = create_sample_order().json()
    response = advance_order_to(created["id"], "INVALID_STATUS")
    assert response.status_code == 422


# ── Full Lifecycle ────────────────────────────────────────────────────────────

def test_full_order_lifecycle_with_payments():
    """
    End-to-end: place order → pay in parts → scheduler promotes →
    ship → deliver → return → refund
    """
    # Place order
    order_id = create_sample_order().json()["id"]
    order = client.get(f"/orders/{order_id}").json()
    assert order["status"] == "PENDING"
    assert order["paid_amount"] == 0.0

    # Partial payments
    pay(order_id, 500.00)
    pay(order_id, 549.99)
    order = client.get(f"/orders/{order_id}").json()
    assert order["paid_amount"] == pytest.approx(1049.99)
    assert order["remaining_amount"] == pytest.approx(0.0)
    assert order["status"] == "PENDING"  # Still PENDING until scheduler runs

    # Scheduler promotes
    db = TestingSessionLocal()
    try:
        crud.promote_pending_orders(db)
    finally:
        db.close()
    assert client.get(f"/orders/{order_id}").json()["status"] == "PROCESSING"

    # Rest of lifecycle
    for expected in ["SHIPPED", "DELIVERED", "RETURN_REQUESTED", "REFUNDED"]:
        response = advance_order_to(order_id, expected)
        assert response.status_code == 200
        assert response.json()["status"] == expected


# ── Cancel Order ──────────────────────────────────────────────────────────────

def test_cancel_pending_order():
    created = create_sample_order().json()
    response = client.delete(f"/orders/{created['id']}/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"


def test_cancel_non_pending_order():
    order_id = create_sample_order().json()["id"]
    advance_order_to(order_id, "PROCESSING")
    response = client.delete(f"/orders/{order_id}/cancel")
    assert response.status_code == 400
    assert "PENDING" in response.json()["detail"]


def test_cancel_order_not_found():
    response = client.delete("/orders/00000000-0000-0000-0000-000000000000/cancel")
    assert response.status_code == 404


# ── Chat Endpoint ─────────────────────────────────────────────────────────────

def test_chat_without_api_key():
    with patch("app.routers.chat.settings") as mock_settings:
        mock_settings.ANTHROPIC_API_KEY = None
        response = client.post("/chat/", json={
            "messages": [{"role": "user", "content": "Hello"}]
        })
    assert response.status_code == 200
    assert "reply" in response.json()
    assert "support@swiftcart.in" in response.json()["reply"]


# ── Health Check ──────────────────────────────────────────────────────────────

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
