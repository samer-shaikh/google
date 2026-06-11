"""
app/services/llm_provider.py

Unified LLM provider interface — single entry point for ALL LLM calls.

Usage:
    from app.services.llm_provider import generate_response

    # Use default model (Gemini unless DEFAULT_MODEL is overridden in .env)
    response = generate_response("Explain machine learning")

    # Explicitly select a provider
    response = generate_response("Explain machine learning", model="gemini")
    response = generate_response("Explain machine learning", model="qwen")

    # Qwen sub-model (returned by model_router.get_model())
    response = generate_response("Explain ML", model="qwen-plus")
    response = generate_response("Explain ML", model="qwen-max")

Supported model strings:
    "gemini"             — Google Gemini 2.5 Flash  (DEFAULT)
    "qwen"               — Alibaba Qwen via DashScope (default sub-model: qwen-plus)
    "qwen-plus"          — Qwen Plus (fast, smart)
    "qwen-max"           — Qwen Max (most capable)

Adding a new provider:
    1. Create app/services/<name>_service.py with generate_response(prompt) -> str
    2. Add its key to SUPPORTED_PROVIDERS and detection logic in _resolve_provider()
    3. Add a branch in _dispatch()
    4. Add key validation in _check_api_key()
    5. Update .env.example and README.md

Environment variables:
    DEFAULT_MODEL      — "gemini" or "qwen" (default: "gemini")
    GEMINI_API_KEY     — required when model="gemini"
    QWEN_API_KEY       — required when model="qwen" / "qwen-plus" / "qwen-max"
"""
import os
import logging
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

# ── Provider keys (high-level names) ─────────────────────────────────────────
SUPPORTED_PROVIDERS = {"gemini", "qwen"}

# Qwen sub-model names that model_router may return
_QWEN_MODEL_NAMES = {"qwen", "qwen-plus", "qwen-max", "qwen-turbo"}

# Default provider — read from env, fall back to "gemini"
DEFAULT_MODEL: str = os.getenv("DEFAULT_MODEL", "gemini").lower().strip()


# ── Provider detection ────────────────────────────────────────────────────────

def _resolve_provider(model: str) -> tuple[str, str]:
    """
    Given a model string (could be a provider key OR a sub-model name),
    return (provider_key, sub_model_name).

    Examples:
        "gemini"    → ("gemini", "gemini-2.5-flash")
        "qwen"      → ("qwen",   "qwen-plus")
        "qwen-plus" → ("qwen",   "qwen-plus")
        "qwen-max"  → ("qwen",   "qwen-max")
    """
    m = model.lower().strip()

    if m == "gemini":
        return ("gemini", "gemini-2.5-flash")

    if m in _QWEN_MODEL_NAMES:
        # If caller just passed "qwen", default to qwen-plus
        sub = m if m != "qwen" else "qwen-plus"
        return ("qwen", sub)

    raise ValueError(
        f"Unsupported model '{model}'. "
        f"Supported: {sorted(SUPPORTED_PROVIDERS)} or Qwen sub-models "
        f"{sorted(_QWEN_MODEL_NAMES)}. "
        f"Check DEFAULT_MODEL in .env."
    )


# ── Internal dispatch ─────────────────────────────────────────────────────────

def _dispatch(provider: str, sub_model: str, prompt: str) -> str:
    """Route prompt to the correct provider module."""
    if provider == "gemini":
        from app.services.gemini_service import generate_response as _gemini
        return _gemini(prompt)

    if provider == "qwen":
        from app.services.qwen_service import generate_response as _qwen
        return _qwen(prompt, sub_model)

    raise ValueError(f"Unknown provider '{provider}'")  # should never reach here


# ── Public API ────────────────────────────────────────────────────────────────

def generate_response(prompt: str, model: str | None = None) -> str:
    """
    Generate a response from the specified LLM provider.

    Args:
        prompt: The text prompt to send to the model.
        model:  Provider key or sub-model name.
                Supported values: "gemini", "qwen", "qwen-plus", "qwen-max"
                If None/omitted, uses DEFAULT_MODEL from .env (default: "gemini").

    Returns:
        The model's response as a plain string.

    Raises:
        ValueError:   Unsupported model name.
        RuntimeError: Required API key missing.
        Exception:    Propagates API-level errors (rate limits, network, etc.)
    """
    resolved = (model or DEFAULT_MODEL).lower().strip()

    try:
        provider, sub_model = _resolve_provider(resolved)
    except ValueError:
        raise ValueError(
            f"Unsupported model '{resolved}'. "
            f"Supported: {sorted(SUPPORTED_PROVIDERS | _QWEN_MODEL_NAMES)}. "
            f"Check DEFAULT_MODEL in .env."
        )

    _check_api_key(provider)

    log.debug(f"[llm_provider] provider='{provider}' sub_model='{sub_model}'")

    try:
        return _dispatch(provider, sub_model, prompt)
    except Exception as e:
        log.error(f"[llm_provider] provider='{provider}' failed: {e}")
        raise


# ── Key validation ────────────────────────────────────────────────────────────

def _check_api_key(provider: str) -> None:
    """Raise RuntimeError early if the required API key is missing."""
    if provider == "gemini":
        key = os.getenv("GEMINI_API_KEY", "").strip()
        if not key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set in .env. "
                "Get a free key at https://aistudio.google.com/apikey"
            )

    elif provider == "qwen":
        key = os.getenv("QWEN_API_KEY", "").strip()
        if not key:
            raise RuntimeError(
                "QWEN_API_KEY is not set in .env. "
                "Get a key at https://dashscope-intl.aliyuncs.com"
            )


# ── Convenience helpers ───────────────────────────────────────────────────────

def get_default_model() -> str:
    """Return the currently configured default provider name."""
    return DEFAULT_MODEL


def list_supported_models() -> list[str]:
    """Return a sorted list of all supported model/provider keys."""
    return sorted(SUPPORTED_PROVIDERS | _QWEN_MODEL_NAMES)
