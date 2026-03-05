import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import Base, get_db
from app.models import OrderStatus

# Use an in-memory SQLite DB for tests (no Postgres needed to run tests)
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


client = TestClient(app)


# ---------- Helpers ----------

def create_sample_order(customer_name="John Doe", customer_email="john@example.com"):
    return client.post("/orders/", json={
        "customer_name": customer_name,
        "customer_email": customer_email,
        "items": [
            {"product_name": "Laptop", "quantity": 1, "unit_price": 999.99},
            {"product_name": "Mouse", "quantity": 2, "unit_price": 25.00},
        ]
    })


# ---------- Create Order Tests ----------

def test_create_order_success():
    response = create_sample_order()
    assert response.status_code == 201
    data = response.json()
    assert data["customer_name"] == "John Doe"
    assert data["status"] == "PENDING"
    assert data["total_amount"] == pytest.approx(1049.99)
    assert len(data["items"]) == 2


def test_create_order_empty_items():
    response = client.post("/orders/", json={
        "customer_name": "Jane",
        "customer_email": "jane@example.com",
        "items": []
    })
    assert response.status_code == 422


def test_create_order_invalid_quantity():
    response = client.post("/orders/", json={
        "customer_name": "Jane",
        "customer_email": "jane@example.com",
        "items": [{"product_name": "Book", "quantity": 0, "unit_price": 10.0}]
    })
    assert response.status_code == 422


def test_create_order_invalid_price():
    response = client.post("/orders/", json={
        "customer_name": "Jane",
        "customer_email": "jane@example.com",
        "items": [{"product_name": "Book", "quantity": 1, "unit_price": -5.0}]
    })
    assert response.status_code == 422


# ---------- Get Order Tests ----------

def test_get_order_success():
    created = create_sample_order().json()
    response = client.get(f"/orders/{created['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_order_not_found():
    response = client.get("/orders/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


# ---------- List Orders Tests ----------

def test_list_orders():
    create_sample_order()
    create_sample_order("Jane Doe", "jane@example.com")
    response = client.get("/orders/")
    assert response.status_code == 200
    assert len(response.json()) == 2


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


# ---------- Update Order Status Tests ----------

def test_update_order_status():
    created = create_sample_order().json()
    response = client.patch(f"/orders/{created['id']}/status", json={"status": "PROCESSING"})
    assert response.status_code == 200
    assert response.json()["status"] == "PROCESSING"


def test_update_order_status_not_found():
    response = client.patch(
        "/orders/00000000-0000-0000-0000-000000000000/status",
        json={"status": "SHIPPED"}
    )
    assert response.status_code == 404


def test_update_order_invalid_status():
    created = create_sample_order().json()
    response = client.patch(f"/orders/{created['id']}/status", json={"status": "INVALID"})
    assert response.status_code == 422


# ---------- Cancel Order Tests ----------

def test_cancel_pending_order():
    created = create_sample_order().json()
    response = client.delete(f"/orders/{created['id']}/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"


def test_cancel_non_pending_order():
    created = create_sample_order().json()
    # Move to PROCESSING first
    client.patch(f"/orders/{created['id']}/status", json={"status": "PROCESSING"})
    # Now try to cancel
    response = client.delete(f"/orders/{created['id']}/cancel")
    assert response.status_code == 400
    assert "PENDING" in response.json()["detail"]


def test_cancel_order_not_found():
    response = client.delete("/orders/00000000-0000-0000-0000-000000000000/cancel")
    assert response.status_code == 404


# ---------- Health Check ----------

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
