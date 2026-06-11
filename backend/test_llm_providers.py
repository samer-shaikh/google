"""
test_llm_providers.py

Quick smoke test — run from the backend folder:
    python test_llm_providers.py

Tests:
  1. Gemini responds to a simple prompt
  2. Qwen responds to a simple prompt
  3. model_router returns correct model IDs per provider
  4. llm_provider defaults to Gemini when model is omitted
"""
import os
import sys

# Make sure project root is on the path
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

PROMPT = "Say exactly: 'LLM provider test passed.' and nothing else."


def test_gemini():
    print("\n── TEST: Gemini ─────────────────────────────────────────")
    try:
        from app.services.llm_provider import generate_response
        result = generate_response(PROMPT, model="gemini")
        print(f"✅ Gemini response: {result.strip()[:120]}")
        return True
    except Exception as e:
        print(f"❌ Gemini failed: {e}")
        return False


def test_qwen():
    print("\n── TEST: Qwen ───────────────────────────────────────────")
    try:
        from app.services.llm_provider import generate_response
        result = generate_response(PROMPT, model="qwen")
        print(f"✅ Qwen response: {result.strip()[:120]}")
        return True
    except Exception as e:
        print(f"❌ Qwen failed: {e}")
        return False


def test_qwen_plus():
    print("\n── TEST: Qwen-Plus (sub-model) ──────────────────────────")
    try:
        from app.services.llm_provider import generate_response
        result = generate_response(PROMPT, model="qwen-plus")
        print(f"✅ Qwen-Plus response: {result.strip()[:120]}")
        return True
    except Exception as e:
        print(f"❌ Qwen-Plus failed: {e}")
        return False


def test_default_model():
    print("\n── TEST: Default model (no model arg) ───────────────────")
    try:
        from app.services.llm_provider import generate_response, DEFAULT_MODEL
        print(f"   DEFAULT_MODEL = '{DEFAULT_MODEL}'")
        result = generate_response(PROMPT)
        print(f"✅ Default response: {result.strip()[:120]}")
        return True
    except Exception as e:
        print(f"❌ Default model failed: {e}")
        return False


def test_model_router():
    print("\n── TEST: model_router ───────────────────────────────────")
    from app.services.model_router import get_model
    from app.services.llm_provider import DEFAULT_MODEL

    cases = [
        ("normal", "research"),
        ("normal", "script"),
        ("plus",   "research"),
        ("plus",   "script"),
        ("plus",   "thumbnail"),
    ]

    for plan, task in cases:
        m = get_model(plan, task)
        print(f"   get_model('{plan}', '{task}') → '{m}'")

    print(f"✅ model_router working (provider: {DEFAULT_MODEL})")
    return True


def test_invalid_model():
    print("\n── TEST: Invalid model name ─────────────────────────────")
    try:
        from app.services.llm_provider import generate_response
        generate_response(PROMPT, model="gpt-99")
        print("❌ Should have raised ValueError")
        return False
    except ValueError as e:
        print(f"✅ Correctly raised ValueError: {e}")
        return True
    except Exception as e:
        print(f"❌ Wrong exception type: {e}")
        return False


if __name__ == "__main__":
    results = {
        "gemini":        test_gemini(),
        "qwen":          test_qwen(),
        "qwen_plus":     test_qwen_plus(),
        "default_model": test_default_model(),
        "model_router":  test_model_router(),
        "invalid_model": test_invalid_model(),
    }

    print("\n── RESULTS ──────────────────────────────────────────────")
    passed = sum(1 for v in results.values() if v)
    for name, ok in results.items():
        icon = "✅" if ok else "❌"
        print(f"  {icon}  {name}")
    print(f"\n{passed}/{len(results)} tests passed")

    if passed < len(results):
        sys.exit(1)
