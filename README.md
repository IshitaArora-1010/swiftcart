# SwiftCart — Order Processing System

A full-stack e-commerce order processing system with a customer storefront, admin dashboard, and AI-powered customer support.

## Tech Stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI (Python 3.12) |
| Database | PostgreSQL 16 + SQLAlchemy ORM |
| Frontend | Vanilla HTML/CSS/JS (no framework) |
| AI Support | Claude API via FastAPI proxy |
| Infrastructure | Docker + Docker Compose |
| Testing | Pytest (SQLite in-memory) |

---

## Quick Start

**Prerequisites:** Docker Desktop installed and running.

```bash
# 1. Copy env file and add your Anthropic API key
cp .env.example .env

# 2. Start everything
docker-compose up --build
```

| URL | Description |
|---|---|
| http://localhost:8000 | Customer storefront |
| http://localhost:8000/admin | Admin dashboard (admin@swiftcart.com / Admin@123) |
| http://localhost:8000/docs | Swagger API docs |

---

## Features

### Customer Storefront
- Sign up / sign in with persistent session
- Home page with hero, category grid, featured products
- 29-product catalogue across 6 categories with filters, sort, and search
- Shopping cart with live order summary and checkout
- Order tracking by ID with visual status timeline
- Return request for delivered orders
- Customer care page with email/WhatsApp contact + AI chat support

### Admin Dashboard
- Live stats: total orders, pending, shipped, revenue, return requests
- Manage orders filtered by status (All / Pending / Processing / Shipped / Delivered / Returns / Refunded / Cancelled)
- Search orders by customer name or email
- One-click status updates with smart action buttons per status

### Backend API
- Full order lifecycle: create, read, list, update status, cancel
- Background job: auto-promotes PENDING → PROCESSING every 5 minutes (APScheduler)
- AI chat proxy: routes messages to Claude API server-side (key never exposed to browser)

---

## Order Status Flow

```
PENDING → PROCESSING → SHIPPED → DELIVERED
                                     ↓
PENDING → CANCELLED        RETURN_REQUESTED → REFUNDED
```

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/orders/` | Create order with multiple items |
| `GET` | `/orders/` | List orders (optional `?status=` filter) |
| `GET` | `/orders/{id}` | Get order details by ID |
| `PATCH` | `/orders/{id}/status` | Update order status |
| `DELETE` | `/orders/{id}/cancel` | Cancel a PENDING order only |
| `POST` | `/chat/` | Proxy message to Claude AI |
| `GET` | `/health` | Health check |

---

## Project Structure

```
order_processing/
├── index.html                  # Customer storefront (SPA)
├── admin.html                  # Admin dashboard
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
└── app/
    ├── main.py                 # FastAPI app + startup lifecycle
    ├── models.py               # SQLAlchemy ORM models
    ├── schemas.py              # Pydantic request/response schemas
    ├── crud.py                 # Database operations
    ├── database.py             # Engine and session setup
    ├── config.py               # Environment variable settings
    ├── scheduler.py            # APScheduler background job
    └── routers/
        ├── orders.py           # Order CRUD endpoints
        └── chat.py             # AI chat proxy endpoint
```

---

## Running Tests

Tests use SQLite in-memory — no running server or Postgres needed.

```bash
pip install pytest pytest-asyncio httpx
pytest tests/ -v
```

---

## Stopping

```bash
# Stop (data preserved):
docker-compose down

# Stop and wipe database:
docker-compose down -v
```
