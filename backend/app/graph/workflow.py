from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt

from app.graph.state import AgentState

from app.agents.research_agent import research_agent
from app.agents.video_idea_agent import video_idea_agent
from app.agents.script_agent import script_agent
from app.agents.thumbnail_agent import thumbnail_agent
from app.agents.seo_agent import seo_agent


# ── Nodes ────────────────────────────────────────────────────────

def research_node(state: AgentState):
    print("[research_node] starting...")
    result = research_agent(state["topic"], state.get("plan", "normal"))
    print("[research_node] done.")
    return {"research": result}


def human_approval_node(state: AgentState):
    """
    LangGraph HITL node.
    interrupt() suspends the graph here and saves the full state
    into the checkpointer under the current thread_id.
    Execution only continues when the /resume endpoint calls
    graph.invoke(Command(resume=<value>), config=same_config).
    The value passed to Command(resume=) is what interrupt() returns.
    """
    print("[human_approval_node] pausing — waiting for human review...")
    approved = interrupt("Research complete. Approve to continue.")
    print(f"[human_approval_node] resumed — approved={approved}")
    return {"human_approved": approved}


def idea_node(state: AgentState):
    print("[idea_node] starting...")
    result = video_idea_agent(
        state["topic"],
        state.get("research", ""),
        state.get("plan", "normal")
    )
    print("[idea_node] done.")
    return {"ideas": result}

def idea_selection_node(state):

    selected = interrupt({
        "type": "idea_selection",
        "ideas": state["ideas"]
    })

    return {
        "selected_idea": selected
    }

def script_node(state: AgentState):
    print("[script_node] starting...")
    result = script_agent(
        state["topic"],
        state.get("research", ""),
        state['selected_idea'],   
        state.get("plan", "normal")
    )
    print("[script_node] done.")
    return {"script": result}


def thumbnail_node(state: AgentState):
    print("[thumbnail_node] starting...")
    result = thumbnail_agent(
        state["topic"],
        state.get("script", ""),
        state.get("plan", "normal")
    )
    print("[thumbnail_node] done.")
    return {"thumbnail": result}


def seo_node(state: AgentState):
    print("[seo_node] starting...")
    result = seo_agent(
        state["topic"],
        state.get("script", ""),
        state.get("plan", "normal")
    )
    print("[seo_node] done.")
    return {"seo": result}


# ── Conditional edge ─────────────────────────────────────────────

def check_approval(state: AgentState):
    if state.get("human_approved") is True:
        return "approved"
    return "rejected"


# ── Graph construction ───────────────────────────────────────────

def _build_graph(checkpointer: MemorySaver):
    builder = StateGraph(AgentState)

    builder.add_node("research",       research_node)
    builder.add_node("human_approval", human_approval_node)
    builder.add_node("ideas",          idea_node)
    builder.add_node("idea_selection",    idea_selection_node)
    builder.add_node("script",         script_node)
    builder.add_node("thumbnail",      thumbnail_node)
    builder.add_node("seo",            seo_node)


    builder.set_entry_point("research")
    builder.add_edge("research", "human_approval")

    builder.add_conditional_edges(
        "human_approval",
        check_approval,
        {"approved": "ideas", "rejected": END}
    )

    builder.add_edge("ideas",     "idea_selection")
    builder.add_edge("idea_selection","script")
    builder.add_edge("script",    "thumbnail")
    builder.add_edge("thumbnail", "seo")
    builder.add_edge("seo",       END)

    return builder.compile(checkpointer=checkpointer)


# ── Singleton — survives uvicorn --reload ────────────────────────
# MemorySaver stores thread state in RAM. If this module is reloaded
# (e.g. by --reload), a new MemorySaver() would lose all saved threads,
# causing /resume to restart from the entry point instead of resuming.
# The singleton guard below prevents re-instantiation on reload.

import sys as _sys

_MODULE = _sys.modules[__name__]

if not hasattr(_MODULE, "_checkpointer"):
    _MODULE._checkpointer = MemorySaver()         # type: ignore[attr-defined]

if not hasattr(_MODULE, "_graph"):
    _MODULE._graph = _build_graph(_MODULE._checkpointer)  # type: ignore[attr-defined]

checkpointer: MemorySaver = _MODULE._checkpointer  # type: ignore[attr-defined]
graph = _MODULE._graph                              # type: ignore[attr-defined]
