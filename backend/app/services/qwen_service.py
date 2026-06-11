"""
app/services/qwen_service.py

Alibaba Qwen provider via DashScope — low-level implementation.

Do NOT import this directly in agents or routes.
Use the unified interface instead:

    from app.services.llm_provider import generate_response
    result = generate_response(prompt, model="qwen")        # uses qwen-plus
    result = generate_response(prompt, model="qwen-max")    # uses qwen-max
"""
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

_DASHSCOPE_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
_DEFAULT_QWEN_MODEL = "qwen-plus"


def generate_response(prompt: str, model: str = _DEFAULT_QWEN_MODEL) -> str:
    """
    Send a prompt to Qwen via DashScope and return the response text.

    Args:
        prompt: The text prompt.
        model:  DashScope model ID — "qwen-plus", "qwen-max", "qwen-turbo".
                Defaults to "qwen-plus" if not specified.

    This is the low-level provider function.
    Prefer calling llm_provider.generate_response(prompt, model="qwen").
    """
    api_key = os.getenv("QWEN_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "QWEN_API_KEY is not set in .env. "
            "Get a key at https://dashscope-intl.aliyuncs.com"
        )

    print(f"[qwen_service] model={model}")

    llm = ChatOpenAI(
        api_key=api_key,  # type: ignore[arg-type]
        base_url=_DASHSCOPE_BASE_URL,
        model=model,
    )

    response = llm.invoke(prompt).content
    return str(response)
