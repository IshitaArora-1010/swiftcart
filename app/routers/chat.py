import logging
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List
import anthropic

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["Chat"])


class ChatMessage(BaseModel):
    """A single message in the conversation history."""
    role: str    # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    """
    Incoming chat request from the frontend.
    The full conversation history is sent each time since the API is stateless.
    """
    messages: List[ChatMessage]


# System prompt defines the AI's persona and knowledge about SwiftCart.
# Kept server-side so it cannot be tampered with from the browser.
SYSTEM_PROMPT = """You are a friendly, helpful customer support assistant for SwiftCart, a premium Indian e-commerce platform.

Key info about SwiftCart:
- Categories: Electronics, Fashion, Home & Kitchen, Books, Sports, Beauty
- Delivery: 3-5 business days standard, 1-2 days express
- Free delivery on orders above ₹999
- 7-day return policy for delivered orders
- Support email: support@swiftcart.in
- To track orders: customers go to the Track Order page and paste their Order ID
- To cancel: only PENDING orders can be cancelled from the Track Order page
- Returns: only DELIVERED orders can request returns from the Track Order page
- Refunds processed within 5-7 business days after return approval
- Currency is Indian Rupees (₹)

Be warm, concise, and helpful. Keep responses short and conversational."""


@router.post("/")
def chat(req: ChatRequest):
    """
    Proxy endpoint that forwards chat messages to the Anthropic Claude API.
    The API key is kept server-side — never exposed to the browser.
    Gracefully falls back to a helpful message if the key is missing or invalid.
    """
    if not settings.ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY is not set in environment")
        return {
            "reply": "AI chat is not configured yet. In the meantime, "
                     "email us at support@swiftcart.in — we respond within 24 hours! 📧"
        }

    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        messages = [{"role": m.role, "content": m.content} for m in req.messages]

        response = client.messages.create(
            model="claude-3-haiku-20240307",  # Fast, cost-efficient model for support chat
            max_tokens=600,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
        return {"reply": response.content[0].text}

    except anthropic.AuthenticationError as e:
        logger.error(f"Anthropic auth error: {e}")
        return {"reply": "There's an issue with the chat configuration. Please contact support@swiftcart.in 📧"}

    except anthropic.NotFoundError as e:
        logger.error(f"Anthropic model not found: {e}")
        return {"reply": "Chat service is temporarily unavailable. Please email support@swiftcart.in 📧"}

    except Exception as e:
        logger.error(f"Anthropic unexpected error: {type(e).__name__}: {e}")
        if hasattr(e, "response"):
            logger.error(f"Response body: {e.response.text}")
        return {"reply": "I'm having a moment! Please email support@swiftcart.in and we'll help you within 24 hours. 📧"}
