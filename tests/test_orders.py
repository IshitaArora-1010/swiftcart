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
    poolclass=StaticPool,  # ← key fix: single shared connection for all test code
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """Replace the real DB session with the test SQLite session for all tests."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


# Swap the real DB dependency with the test one
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
    """Helper to create a standard two-item order used across multiple tests."""
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


# ── Create Order ──────────────────────────────────────────────────────────────

def test_create_order_success():
    """A valid order should be created with PENDING status and correct total."""
    response = create_sample_order()
    assert response.status_code == 201
    data = response.json()
    assert data["customer_name"] == "John Doe"
    assert data["status"] == "PENDING"
    assert data["total_amount"] == pytest.approx(1049.99)  # 999.99 + (2 × 25.00)
    assert len(data["items"]) == 2


def test_create_order_total_amount_calculated_correctly():
    """total_amount should be sum of quantity × unit_price across all items."""
    response = client.post("/orders/", json={
        "customer_name": "Test",
        "customer_email": "test@example.com",
        "items": [
            {"product_name": "Item A", "quantity": 3, "unit_price": 100.00},
            {"product_name": "Item B", "quantity": 2, "unit_price": 50.00},
        ]
    })
    assert response.status_code == 201
    assert response.json()["total_amount"] == pytest.approx(400.00)  # 300 + 100


def test_create_order_empty_items():
    """An order with no items should be rejected with 422 Unprocessable Entity."""
    response = client.post("/orders/", json={
        "customer_name": "Jane",
        "customer_email": "jane@example.com",
        "items": []
    })
    assert response.status_code == 422


def test_create_order_invalid_quantity():
    """Quantity of 0 should be rejected."""
    response = client.post("/orders/", json={
        "customer_name": "Jane",
        "customer_email": "jane@example.com",
        "items": [{"product_name": "Book", "quantity": 0, "unit_price": 10.0}]
    })
    assert response.status_code == 422


def test_create_order_negative_quantity():
    """Negative quantity should be rejected."""
    response = client.post("/orders/", json={
        "customer_name": "Jane",
        "customer_email": "jane@example.com",
        "items": [{"product_name": "Book", "quantity": -1, "unit_price": 10.0}]
    })
    assert response.status_code == 422


def test_create_order_invalid_price():
    """Negative unit price should be rejected."""
    response = client.post("/orders/", json={
        "customer_name": "Jane",
        "customer_email": "jane@example.com",
        "items": [{"product_name": "Book", "quantity": 1, "unit_price": -5.0}]
    })
    assert response.status_code == 422


def test_create_order_zero_price():
    """Zero unit price should be rejected."""
    response = client.post("/orders/", json={
        "customer_name": "Jane",
        "customer_email": "jane@example.com",
        "items": [{"product_name": "Book", "quantity": 1, "unit_price": 0}]
    })
    assert response.status_code == 422


# ── Get Order ─────────────────────────────────────────────────────────────────

def test_get_order_success():
    """Getting an order by its ID should return the full order with items."""
    created = create_sample_order().json()
    response = client.get(f"/orders/{created['id']}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == created["id"]
    assert len(data["items"]) == 2


def test_get_order_not_found():
    """A nil UUID should return 404."""
    response = client.get("/orders/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


# ── List Orders ───────────────────────────────────────────────────────────────

def test_list_orders():
    """All created orders should appear in the list."""
    create_sample_order()
    create_sample_order("Jane Doe", "jane@example.com")
    response = client.get("/orders/")
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_list_orders_filter_by_status():
    """Filtering by PENDING should only return PENDING orders."""
    create_sample_order()
    response = client.get("/orders/?status=PENDING")
    assert response.status_code == 200
    assert all(o["status"] == "PENDING" for o in response.json())


def test_list_orders_filter_no_results():
    """Filter by a status that no orders have — should return empty list, not 404."""
    create_sample_order()
    response = client.get("/orders/?status=DELIVERED")
    assert response.status_code == 200
    assert response.json() == []


def test_list_orders_filter_return_requested():
    """Filtering by RETURN_REQUESTED should only return those orders."""
    order_id = create_sample_order().json()["id"]
    advance_order_to(order_id, "DELIVERED")
    advance_order_to(order_id, "RETURN_REQUESTED")
    response = client.get("/orders/?status=RETURN_REQUESTED")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["status"] == "RETURN_REQUESTED"


def test_list_orders_filter_refunded():
    """Filtering by REFUNDED should only return those orders."""
    order_id = create_sample_order().json()["id"]
    advance_order_to(order_id, "DELIVERED")
    advance_order_to(order_id, "RETURN_REQUESTED")
    advance_order_to(order_id, "REFUNDED")
    response = client.get("/orders/?status=REFUNDED")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["status"] == "REFUNDED"


# ── Update Status ─────────────────────────────────────────────────────────────

def test_update_order_status_to_processing():
    created = create_sample_order().json()
    response = advance_order_to(created["id"], "PROCESSING")
    assert response.status_code == 200
    assert response.json()["status"] == "PROCESSING"


def test_update_order_status_to_shipped():
    order_id = create_sample_order().json()["id"]
    advance_order_to(order_id, "PROCESSING")
    response = advance_order_to(order_id, "SHIPPED")
    assert response.status_code == 200
    assert response.json()["status"] == "SHIPPED"


def test_update_order_status_to_delivered():
    order_id = create_sample_order().json()["id"]
    advance_order_to(order_id, "PROCESSING")
    advance_order_to(order_id, "SHIPPED")
    response = advance_order_to(order_id, "DELIVERED")
    assert response.status_code == 200
    assert response.json()["status"] == "DELIVERED"


def test_update_order_status_to_return_requested():
    """Customer should be able to request a return after delivery."""
    order_id = create_sample_order().json()["id"]
    advance_order_to(order_id, "DELIVERED")
    response = advance_order_to(order_id, "RETURN_REQUESTED")
    assert response.status_code == 200
    assert response.json()["status"] == "RETURN_REQUESTED"


def test_update_order_status_to_refunded():
    """Admin should be able to mark a return as refunded."""
    order_id = create_sample_order().json()["id"]
    advance_order_to(order_id, "DELIVERED")
    advance_order_to(order_id, "RETURN_REQUESTED")
    response = advance_order_to(order_id, "REFUNDED")
    assert response.status_code == 200
    assert response.json()["status"] == "REFUNDED"


def test_update_order_status_not_found():
    """Updating a non-existent order should return 404."""
    response = client.patch(
        "/orders/00000000-0000-0000-0000-000000000000/status",
        json={"status": "SHIPPED"}
    )
    assert response.status_code == 404


def test_update_order_invalid_status():
    """An unrecognised status value should be rejected with 422."""
    created = create_sample_order().json()
    response = advance_order_to(created["id"], "INVALID_STATUS")
    assert response.status_code == 422


# ── Full Lifecycle ────────────────────────────────────────────────────────────

def test_full_order_lifecycle():
    """End-to-end: order goes through every status in the normal flow."""
    order_id = create_sample_order().json()["id"]

    for expected_status in ["PROCESSING", "SHIPPED", "DELIVERED", "RETURN_REQUESTED", "REFUNDED"]:
        response = advance_order_to(order_id, expected_status)
        assert response.status_code == 200
        assert response.json()["status"] == expected_status


# ── Cancel Order ──────────────────────────────────────────────────────────────

def test_cancel_pending_order():
    """A PENDING order should be cancellable."""
    created = create_sample_order().json()
    response = client.delete(f"/orders/{created['id']}/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"


def test_cancel_non_pending_order():
    """Cancelling an order that has moved past PENDING should return 400."""
    order_id = create_sample_order().json()["id"]
    advance_order_to(order_id, "PROCESSING")
    response = client.delete(f"/orders/{order_id}/cancel")
    assert response.status_code == 400
    assert "PENDING" in response.json()["detail"]


def test_cancel_delivered_order():
    """A delivered order cannot be cancelled."""
    order_id = create_sample_order().json()["id"]
    advance_order_to(order_id, "DELIVERED")
    response = client.delete(f"/orders/{order_id}/cancel")
    assert response.status_code == 400


def test_cancel_order_not_found():
    """Cancelling a non-existent order should return 404."""
    response = client.delete("/orders/00000000-0000-0000-0000-000000000000/cancel")
    assert response.status_code == 404


# ── Scheduler / promote_pending_orders ───────────────────────────────────────

def test_promote_pending_orders():
    """promote_pending_orders should move all PENDING orders to PROCESSING."""
    create_sample_order()
    create_sample_order("Jane", "jane@example.com")

    db = TestingSessionLocal()
    try:
        count = crud.promote_pending_orders(db)
    finally:
        db.close()

    assert count == 2
    response = client.get("/orders/?status=PROCESSING")
    assert len(response.json()) == 2


def test_promote_pending_orders_skips_non_pending():
    """promote_pending_orders should not touch orders that aren't PENDING."""
    order_id = create_sample_order().json()["id"]
    advance_order_to(order_id, "SHIPPED")  # Manually advance one order

    create_sample_order("Jane", "jane@example.com")  # Leave one as PENDING

    db = TestingSessionLocal()
    try:
        count = crud.promote_pending_orders(db)
    finally:
        db.close()

    assert count == 1  # Only the PENDING one should be promoted
    assert client.get("/orders/?status=SHIPPED").json()[0]["status"] == "SHIPPED"


def test_promote_pending_orders_no_pending():
    """promote_pending_orders should return 0 when there are no PENDING orders."""
    db = TestingSessionLocal()
    try:
        count = crud.promote_pending_orders(db)
    finally:
        db.close()

    assert count == 0


# ── Chat Endpoint ─────────────────────────────────────────────────────────────

def test_chat_without_api_key():
    """Chat should return a friendly fallback message when API key is not set."""
    with patch("app.routers.chat.settings") as mock_settings:
        mock_settings.ANTHROPIC_API_KEY = None
        response = client.post("/chat/", json={
            "messages": [{"role": "user", "content": "Hello"}]
        })
    assert response.status_code == 200
    assert "reply" in response.json()
    assert "support@swiftcart.in" in response.json()["reply"]


def test_chat_request_structure():
    """Chat endpoint should accept a valid messages array and return a reply key."""
    with patch("app.routers.chat.settings") as mock_settings:
        mock_settings.ANTHROPIC_API_KEY = None
        response = client.post("/chat/", json={
            "messages": [
                {"role": "user", "content": "Where is my order?"},
            ]
        })
    assert response.status_code == 200
    assert "reply" in response.json()


# ── Health Check ──────────────────────────────────────────────────────────────

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
