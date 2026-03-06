from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

# Create the SQLAlchemy engine using the DATABASE_URL from environment variables.
# In Docker, this points to the PostgreSQL container; locally it points to a local DB.
engine = create_engine(settings.DATABASE_URL)

# Session factory — each request gets its own session (see get_db below)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for all ORM models (Order, OrderItem inherit from this)
Base = declarative_base()

def get_db():
    """
    FastAPI dependency that provides a database session per request.
    Automatically closes the session after the request completes,
    even if an exception is raised.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
