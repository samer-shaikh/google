"""
app/services/model_router.py

Maps (plan, task) → the model string to pass to llm_provider.generate_response().

The returned string is ALWAYS a value that llm_provider._resolve_provider()
understands:
  - "gemini"     → routes to Gemini 2.5 Flash
  - "qwen-plus"  → routes to Qwen Plus via DashScope
  - "qwen-max"   → routes to Qwen Max via DashScope

The active provider is determined by DEFAULT_MODEL in .env.
Agents do NOT need to know which provider is active — they just call:

    from app.services.model_router import get_model
    from app.services.llm_provider import generate_response

    model = get_model(plan, task)
    result = generate_response(prompt, model)

Usage examples:
    get_model("normal", "research")  → "gemini" (or "qwen-plus" if DEFAULT_MODEL=qwen)
    get_model("plus",   "script")    → "gemini" (or "qwen-max" if DEFAULT_MODEL=qwen)
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Qwen sub-model map ────────────────────────────────────────────────────────
# Returns DashScope model IDs that llm_provider recognises as Qwen variants.
_QWEN_MODELS: dict[str, dict[str, str]] = {
    "normal": {"default": "qwen-plus"},
    "pro":    {"default": "qwen-plus"},
    "plus": {
        "research":         "qwen-max",
        "script":           "qwen-max",
        "video_idea":       "qwen-plus",
        "seo":              "qwen-plus",
        "thumbnail":        "qwen-plus",
        "upload_optimizer": "qwen-plus",
        "youtube":          "qwen-plus",
        "default":          "qwen-plus",
    },
}

# ── Gemini model map ──────────────────────────────────────────────────────────
# Returns "gemini" for all tasks (llm_provider maps this to gemini-2.5-flash).
# Extend this to "gemini-pro" etc. when new Gemini tiers are added.
_GEMINI_MODELS: dict[str, dict[str, str]] = {
    "normal": {"default": "gemini"},
    "pro":    {"default": "gemini"},
    "plus": {
        "research":         "gemini",
        "script":           "gemini",
        "video_idea":       "gemini",
        "seo":              "gemini",
        "thumbnail":        "gemini",
        "upload_optimizer": "gemini",
        "youtube":          "gemini",
        "default":          "gemini",
    },
}

# ── Active provider ───────────────────────────────────────────────────────────
_DEFAULT_PROVIDER: str = os.getenv("DEFAULT_MODEL", "gemini").lower().strip()


def get_model(plan: str, task: str) -> str:
    """
    Return the model identifier for the given plan and task.

    The returned string is passed directly to llm_provider.generate_response()
    as the `model` argument. llm_provider handles all routing from there.

    Args:
        plan: "normal", "pro", or "plus"
        task: "research", "script", "video_idea", "seo",
              "thumbnail", "upload_optimizer", "youtube"

    Returns:
        "gemini" (when DEFAULT_MODEL=gemini)
        or a Qwen sub-model ID like "qwen-plus" / "qwen-max"
        (when DEFAULT_MODEL=qwen)
    """
    provider = _DEFAULT_PROVIDER

    if provider == "gemini":
        table = _GEMINI_MODELS
    elif provider in ("qwen", "qwen-plus", "qwen-max"):
        table = _QWEN_MODELS
    else:
        # Unknown provider — fall back to Gemini safely
        table = _GEMINI_MODELS

    if plan in ("normal", "pro"):
        return table[plan]["default"]

    # "plus" plan — task-specific selection
    plus_table = table.get("plus", {})
    return plus_table.get(task, plus_table.get("default", "gemini"))
