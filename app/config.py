from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables or a .env file.
    All sensitive values (API keys, DB credentials) must live in .env — never hardcoded.
    """
    # PostgreSQL connection string — overridden by docker-compose for the container
    DATABASE_URL: str = "postgresql://postgres:password@localhost:5432/order_processing"

    # Anthropic API key for AI chat support — optional, chat degrades gracefully without it
    ANTHROPIC_API_KEY: Optional[str] = None

    class Config:
        env_file = ".env"       # Load values from .env file if present
        extra = "ignore"        # Silently ignore any extra keys in .env


settings = Settings()
