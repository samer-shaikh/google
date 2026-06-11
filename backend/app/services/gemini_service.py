"""
app/services/gemini_service.py

Google Gemini provider — low-level implementation.

Do NOT import this directly in agents or routes.
Use the unified interface instead:

    from app.services.llm_provider import generate_response
    result = generate_response(prompt, model="gemini")
"""
import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

# Lazy singleton — created on first call to avoid import-time errors
_llm = None


def _get_llm() -> ChatGoogleGenerativeAI:
    global _llm
    if _llm is None:
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. "
                "Get a free key at https://aistudio.google.com/apikey "
                "and add it to your .env file."
            )
        _llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=api_key,
            temperature=0.7,
            max_output_tokens=8192,
        )
    return _llm


def generate_response(prompt: str) -> str:
    """
    Send a prompt to Google Gemini 2.5 Flash and return the response text.

    This is the low-level provider function.
    Prefer calling llm_provider.generate_response(prompt, model="gemini").
    """
    llm = _get_llm()
    response = llm.invoke(prompt)
    return str(response.content)


def reset_client() -> None:
    """Force re-creation of the LLM client on next call (useful for key rotation)."""
    global _llm
    _llm = None
