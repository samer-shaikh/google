from langgraph.graph import StateGraph, END

from app.graph.state import UploadState
from app.agents.upload_optimizer_agent import upload_optimizer_agent


# ── Node ─────────────────────────────────────────────────────────

def upload_optimizer_node(state: UploadState):
    print("[upload_optimizer_node] starting...")
    result = upload_optimizer_agent(
        state["topic"],
        state.get("script", ""),
        state.get("plan", "normal")
    )
    print("[upload_optimizer_node] done.")
    return {"upload": result}


# ── Graph ─────────────────────────────────────────────────────────
# No checkpointer needed — this is a single-shot stateless workflow.
# It runs to completion in one invoke() call with no HITL pauses.

def _build_upload_graph():
    builder = StateGraph(UploadState)
    builder.add_node("upload_optimizer", upload_optimizer_node)
    builder.set_entry_point("upload_optimizer")
    builder.add_edge("upload_optimizer", END)
    return builder.compile()


import sys as _sys
_MODULE = _sys.modules[__name__]

if not hasattr(_MODULE, "_upload_graph"):
    _MODULE._upload_graph = _build_upload_graph()  # type: ignore[attr-defined]

upload_graph = _MODULE._upload_graph               # type: ignore[attr-defined]
