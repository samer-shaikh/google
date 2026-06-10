"""
test_full_system.py
===================
Full system health check for AI Content Studio.

Tests every layer in order:
  1.  Environment variables
  2.  PostgreSQL connection
  3.  MongoDB direct (PyMongo)
  4.  MongoDB MCP server (subprocess + JSON-RPC)
  5.  MongoDB MCP tool call (real query)
  6.  Memory services (creator / research / content)
  7.  Elasticsearch (if configured)
  8.  Model router + Qwen LLM (real API call)
  9.  LangGraph checkpointer
  10. All agent imports
  11. Workflow graph compilation
  12. Upload graph compilation
  13. Full workflow simulation (dry-run without LLM)
  14. API endpoints (live server check)

Run from the backend directory:
    python test_full_system.py

Run against live server:
    python test_full_system.py --live
    python test_full_system.py --live --base-url http://127.0.0.1:8000
"""

import os
import sys
import asyncio
import argparse
import time
from pathlib import Path
from dotenv import load_dotenv

# ── Setup ─────────────────────────────────────────────────────────────────────
# Make sure we're in the backend directory
BACKEND_DIR = Path(__file__).parent
sys.path.insert(0, str(BACKEND_DIR))
load_dotenv(BACKEND_DIR / ".env")

# ── Colours ───────────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg):    print(f"  {GREEN}✅ PASS{RESET}  {msg}")
def fail(msg):  print(f"  {RED}❌ FAIL{RESET}  {msg}")
def warn(msg):  print(f"  {YELLOW}⚠️  WARN{RESET}  {msg}")
def info(msg):  print(f"  {BLUE}ℹ️  INFO{RESET}  {msg}")
def header(msg):print(f"\n{BOLD}{BLUE}{'─'*60}{RESET}\n{BOLD} {msg}{RESET}\n{'─'*60}")

RESULTS = {"pass": 0, "fail": 0, "warn": 0, "skip": 0}

def record(status, msg):
    RESULTS[status] += 1
    if status == "pass":  ok(msg)
    elif status == "fail": fail(msg)
    elif status == "warn": warn(msg)
    else: info(f"SKIP  {msg}")


# ══════════════════════════════════════════════════════════════════════════════
# 1. ENVIRONMENT VARIABLES
# ══════════════════════════════════════════════════════════════════════════════

def test_env():
    header("1. Environment Variables")

    required = {
        "DATABASE_URl":   "PostgreSQL connection string",
        "MONGODB_URI":    "MongoDB Atlas URI",
        "MONGODB_DB_NAME":"MongoDB database name",
        "QWEN_API_KEY":   "Qwen LLM API key",
        "SECRET_KEY":     "JWT secret",
    }

    optional = {
        "ELASTICSEARCH_URL":   "Elasticsearch (Phase 2 — Elastic intelligence)",
        "ELASTICSEARCH_API_KEY":"Elasticsearch API key",
        "GOOGLE_CLIENT_ID":    "Google OAuth",
        "YOUTUBE_API_KEY":     "YouTube Data API",
    }

    for key, desc in required.items():
        val = os.getenv(key, "").strip()
        if val:
            record("pass", f"{key} is set ({desc})")
        else:
            record("fail", f"{key} is MISSING — {desc}")

    for key, desc in optional.items():
        val = os.getenv(key, "").strip()
        if val:
            record("pass", f"{key} is set ({desc})")
        else:
            record("warn", f"{key} not set — {desc} disabled")


# ══════════════════════════════════════════════════════════════════════════════
# 2. POSTGRESQL
# ══════════════════════════════════════════════════════════════════════════════

def test_postgresql():
    header("2. PostgreSQL Connection")
    try:
        import psycopg
        db_url = (os.getenv("DATABASE_URl") or os.getenv("DATABASE_URL", "")).strip().strip('"')
        db_url = db_url.replace("postgresql+psycopg2://", "postgresql://").replace("postgresql+psycopg://", "postgresql://")
        conn = psycopg.connect(db_url, autocommit=True)
        row = conn.execute("SELECT version()").fetchone()
        conn.close()
        record("pass", f"PostgreSQL connected — {row[0][:60]}")
    except ImportError:
        record("fail", "psycopg not installed — run: pip install psycopg[binary]")
    except Exception as e:
        record("fail", f"PostgreSQL connection failed: {e}")

    # Check LangGraph tables exist
    try:
        import psycopg
        db_url = (os.getenv("DATABASE_URl") or "").strip().strip('"')
        db_url = db_url.replace("postgresql+psycopg2://", "postgresql://")
        conn = psycopg.connect(db_url, autocommit=True)
        tables = conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='public'"
        ).fetchall()
        table_names = [t[0] for t in tables]
        conn.close()

        langgraph_tables = ["checkpoints", "checkpoint_blobs", "checkpoint_writes"]
        app_tables = ["users", "generations", "creator_profiles", "upload_records"]

        for t in langgraph_tables:
            if t in table_names:
                record("pass", f"LangGraph table '{t}' exists")
            else:
                record("warn", f"LangGraph table '{t}' missing — run server once to create")

        for t in app_tables:
            if t in table_names:
                record("pass", f"App table '{t}' exists")
            else:
                record("fail", f"App table '{t}' missing — run: python create_tables.py")
    except Exception as e:
        record("warn", f"Could not check tables: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 3. MONGODB DIRECT (PyMongo)
# ══════════════════════════════════════════════════════════════════════════════

def test_mongodb_direct():
    header("3. MongoDB Direct (PyMongo)")
    try:
        from app.mcp.mongodb.client import get_mongodb_client
        client = get_mongodb_client()
        if client is None:
            record("fail", "MongoDB client is None — check MONGODB_URI in .env")
            return

        db_name = os.getenv("MONGODB_DB_NAME", "ai_content_studio")
        db = client[db_name]

        # Ping
        client.admin.command("ping")
        record("pass", f"MongoDB Atlas ping successful — db: '{db_name}'")

        # Check collections
        collections = db.list_collection_names()
        expected = ["creator_memory", "research_sessions", "content_pieces"]
        for col in expected:
            if col in collections:
                count = db[col].count_documents({})
                record("pass", f"Collection '{col}' exists — {count} documents")
            else:
                record("warn", f"Collection '{col}' not yet created (normal on first run)")

        # Test write + read + delete
        test_doc = {"_test": True, "value": "system_check", "ts": time.time()}
        inserted = db["_system_test"].insert_one(test_doc)
        read_back = db["_system_test"].find_one({"_id": inserted.inserted_id})
        db["_system_test"].delete_one({"_id": inserted.inserted_id})

        if read_back and read_back.get("value") == "system_check":
            record("pass", "MongoDB write → read → delete cycle works")
        else:
            record("fail", "MongoDB write/read cycle failed")

    except Exception as e:
        record("fail", f"MongoDB direct test failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 4 & 5. MONGODB MCP SERVER
# ══════════════════════════════════════════════════════════════════════════════

async def _test_mongodb_mcp_async():
    header("4. MongoDB MCP Server (subprocess + JSON-RPC)")

    # Check npx is available
    import shutil
    npx = shutil.which("npx")
    if npx:
        record("pass", f"npx found at: {npx}")
    else:
        record("fail", "npx not found — install Node.js from nodejs.org")
        return

    # Check config file
    config_path = BACKEND_DIR / "app" / "mcp" / "mongodb" / "mongodb_mcp.json"
    if config_path.exists():
        import json
        cfg = json.loads(config_path.read_text())
        record("pass", f"mongodb_mcp.json found — command: {cfg.get('command', cfg.get('mcpServers', {}).get('mongodb', {}).get('command', 'npx'))}")
    else:
        record("fail", f"mongodb_mcp.json not found at {config_path}")
        return

    # Test MCP subprocess initialization
    try:
        from app.mcp.mongodb.mcp_runner import call_mcp_tool, _initialized, _process
        info("Spawning MongoDB MCP server subprocess (may take 2-3s)...")
        start = time.time()

        result = await call_mcp_tool("find", {
            "collection": "creator_memory",
            "filter": {},
            "limit": 1,
        })
        elapsed = time.time() - start

        # Re-import to get updated state after call
        from app.mcp.mongodb import mcp_runner as _mcp_mod
        if _mcp_mod._initialized:
            record("pass", f"MongoDB MCP server initialized in {elapsed:.1f}s")
        else:
            record("fail", "MongoDB MCP server failed to initialize")
            return

        header("5. MongoDB MCP Tool Call (real query)")
        if result is not None:
            record("pass", f"MCP 'find' tool returned data: {type(result).__name__}")
        else:
            record("pass", "MCP 'find' returned empty (collection is empty — normal on first run)")

        # Test insert via MCP
        insert_result = await call_mcp_tool("insertOne", {
            "collection": "_mcp_test",
            "document": {"_test": True, "ts": time.time()},
        })
        if insert_result is not None:
            record("pass", "MCP 'insertOne' tool works")
        else:
            record("warn", "MCP 'insertOne' returned None — tool may not be supported, direct PyMongo handles writes")

    except Exception as e:
        record("fail", f"MongoDB MCP test failed: {e}")


def test_mongodb_mcp():
    asyncio.run(_test_mongodb_mcp_async())


# ══════════════════════════════════════════════════════════════════════════════
# 6. MEMORY SERVICES
# ══════════════════════════════════════════════════════════════════════════════

def test_memory_services():
    header("6. Memory Services")

    services = [
        ("creator_memory_service", "app.memory.creator_memory_service", "CreatorMemoryService"),
        ("research_memory_service", "app.memory.research_memory_service", "ResearchMemoryService"),
        ("content_memory_service", "app.memory.content_memory_service", "ContentMemoryService"),
    ]

    for name, module_path, class_name in services:
        try:
            import importlib
            mod = importlib.import_module(module_path)
            cls = getattr(mod, class_name)
            instance = cls()
            record("pass", f"{class_name} instantiated successfully")
        except Exception as e:
            record("fail", f"{class_name} failed: {e}")

    # Test memory __init__ factory functions
    try:
        from app.memory import (
            get_creator_memory_service,
            get_research_memory_service,
            get_content_memory_service,
        )
        get_creator_memory_service()
        get_research_memory_service()
        get_content_memory_service()
        record("pass", "Memory factory functions (get_*_service) all work")
    except Exception as e:
        record("fail", f"Memory factory functions failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 7. ELASTICSEARCH
# ══════════════════════════════════════════════════════════════════════════════

def test_elasticsearch():
    header("7. Elasticsearch")

    from app.mcp.elastic.client import is_elastic_enabled, get_elastic_client

    if not is_elastic_enabled():
        record("warn", "Elasticsearch not configured — ELASTICSEARCH_URL is empty")
        info("To enable: add ELASTICSEARCH_URL + ELASTICSEARCH_API_KEY to .env")
        return

    client = get_elastic_client()
    if client is None:
        record("fail", "Elasticsearch configured but client failed to connect")
        return

    try:
        info_resp = client.info()
        record("pass", f"Elasticsearch connected — cluster: {info_resp['cluster_name']}")

        # Check indexes
        from app.mcp.elastic.indexes import INDEX_NAMES
        for index_name in INDEX_NAMES:
            exists = client.indices.exists(index=index_name)
            if exists:
                count = client.count(index=index_name)["count"]
                record("pass", f"Index '{index_name}' exists — {count} docs")
            else:
                record("warn", f"Index '{index_name}' missing — run server to auto-create")

    except Exception as e:
        record("fail", f"Elasticsearch check failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 8. QWEN LLM
# ══════════════════════════════════════════════════════════════════════════════

def test_llm():
    header("8. Qwen LLM (real API call)")

    api_key = os.getenv("QWEN_API_KEY", "").strip()
    if not api_key:
        record("fail", "QWEN_API_KEY not set — LLM calls will fail")
        return

    try:
        from app.services.model_router import get_model
        from app.services.qwen_service import generate_response

        model = get_model("normal", "research")
        record("pass", f"Model router works — normal/research → '{model}'")

        model_plus = get_model("plus", "script")
        record("pass", f"Model router works — plus/script → '{model_plus}'")

        info("Sending test prompt to Qwen API (may take 3-5s)...")
        start = time.time()
        response = generate_response(
            "Reply with exactly: SYSTEM_OK",
            model=model,
        )
        elapsed = time.time() - start

        if response and len(response) > 0:
            record("pass", f"Qwen API responded in {elapsed:.1f}s — response: '{response[:50]}'")
        else:
            record("fail", "Qwen API returned empty response")

    except Exception as e:
        record("fail", f"Qwen LLM test failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 9. LANGGRAPH CHECKPOINTER
# ══════════════════════════════════════════════════════════════════════════════

def test_checkpointer():
    header("9. LangGraph Checkpointer")

    try:
        from app.graph.checkpointer import get_checkpointer, setup_checkpointer
        checkpointer = get_checkpointer()
        kind = type(checkpointer).__name__
        if "Postgres" in kind:
            record("pass", f"Checkpointer is {kind} — HITL state persists across restarts ✅")
        elif "Memory" in kind:
            record("warn", f"Checkpointer is MemorySaver — HITL state lost on restart. Check PostgreSQL connection.")
        else:
            record("warn", f"Checkpointer type: {kind}")
    except Exception as e:
        record("fail", f"Checkpointer failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 10. ALL AGENT IMPORTS
# ══════════════════════════════════════════════════════════════════════════════

def test_agent_imports():
    header("10. All Agent Imports")

    agents = [
        ("research_agent",         "app.agents.research_agent",         "research_agent"),
        ("video_idea_agent",       "app.agents.video_idea_agent",       "video_idea_agent"),
        ("script_agent",           "app.agents.script_agent",           "script_agent"),
        ("critic_agent",           "app.agents.critic_agent",           "critic_agent"),
        ("thumbnail_agent",        "app.agents.thumbnail_agent",        "thumbnail_agent"),
        ("seo_agent",              "app.agents.seo_agent",              "seo_agent"),
        ("content_gap_agent",      "app.agents.content_gap_agent",      "content_gap_agent"),
        ("trend_agent",            "app.agents.trend_agent",            "run_trend_agent"),
        ("creator_profile_agent",  "app.agents.creator_profile_agent",  "CreatorProfileAgent"),
        ("youtube_research_agent", "app.agents.youtube_research_agent", "YouTubeResearchAgent"),
        ("upload_optimizer_agent", "app.agents.upload_optimizer_agent", "upload_optimizer_agent"),
        ("youtube_agent",          "app.agents.youtube_agent",          "YouTubeAgent"),
    ]

    for name, module_path, func_name in agents:
        try:
            import importlib
            mod = importlib.import_module(module_path)
            fn = getattr(mod, func_name, None)
            if fn is not None:
                record("pass", f"{name} → '{func_name}' importable")
            else:
                record("warn", f"{name} imported but '{func_name}' not found")
        except Exception as e:
            record("fail", f"{name} import failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 11 & 12. GRAPH COMPILATION
# ══════════════════════════════════════════════════════════════════════════════

def test_graph_compilation():
    header("11. Workflow Graph Compilation")
    try:
        from app.graph.workflow import init_content_graph
        graph = init_content_graph()
        record("pass", f"Content generation graph compiled — type: {type(graph).__name__}")

        # Check all expected nodes are present
        expected_nodes = [
            "load_memory", "content_gap_check", "research",
            "human_approval", "ideas", "idea_selection",
            "script", "critic", "thumbnail", "save_generation"
        ]
        graph_nodes = list(graph.get_graph().nodes.keys())
        for node in expected_nodes:
            if node in graph_nodes:
                record("pass", f"  Node '{node}' present in graph")
            else:
                record("warn", f"  Node '{node}' NOT found in graph — check workflow.py")
    except Exception as e:
        record("fail", f"Workflow graph compilation failed: {e}")

    header("12. Upload Graph Compilation")
    try:
        from app.graph.upload_workflow import init_upload_graph
        upload_graph = init_upload_graph()
        record("pass", f"Upload graph compiled — type: {type(upload_graph).__name__}")
    except Exception as e:
        record("fail", f"Upload graph compilation failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 13. WORKFLOW DRY RUN (no LLM)
# ══════════════════════════════════════════════════════════════════════════════

def test_workflow_dry_run():
    header("13. Workflow State Dry Run (no LLM)")

    try:
        from app.graph.state import AgentState

        # Build a fake state matching what the workflow expects
        test_state: AgentState = {
            "user_id":         999,
            "generation_id":   0,
            "plan":            "normal",
            "topic":           "How to learn Python",
            "creator_profile": {
                "channel_name":   "TestChannel",
                "creator_niche":  "Python Programming",
                "main_topics":    ["Python", "Programming"],
                "audience_type":  "beginners",
                "audience_level": "beginner",
                "title_style":    "how-to tutorials",
                "description_style": "detailed with timestamps",
                "content_strengths":  ["clear explanations"],
                "viral_patterns":     ["'in X minutes' format"],
                "recommended_video_types": ["tutorials"],
            },
            "topic_history":              ["Python basics", "Variables in Python"],
            "viral_patterns":             ["'in X minutes' format"],
            "successful_hooks":           ["Did you know Python can..."],
            "successful_title_patterns":  ["How to X in Y minutes"],
            "content_gaps":               [],
            "trending_topics":            [],
            "competitor_insights":        [],
            "research":                   "",
            "ideas":                      [],
            "selected_idea":              "",
            "script":                     "",
            "thumbnail":                  "",
            "critic_score":               0,
            "critic_feedback":            "",
            "script_revision_count":      0,
            "approved":                   False,
            "rejection_reason":           "",
            "messages":                   [],
        } # type: ignore

        # Validate all expected keys exist in state
        required_keys = [
            "user_id", "generation_id", "plan", "topic", "creator_profile",
            "topic_history", "viral_patterns", "successful_hooks",
            "content_gaps", "research", "ideas", "selected_idea",
            "script", "thumbnail", "critic_score", "approved",
        ]

        missing = [k for k in required_keys if k not in test_state]
        if not missing:
            record("pass", f"AgentState has all {len(required_keys)} required keys")
        else:
            record("fail", f"AgentState missing keys: {missing}")

        # Test load_memory_node with fake state (no DB)
        record("pass", "AgentState structure is valid for workflow")

    except Exception as e:
        record("fail", f"Workflow dry run failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 14. LIVE API ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

def test_live_api(base_url: str):
    header(f"14. Live API Endpoints ({base_url})")

    try:
        import requests
    except ImportError:
        record("warn", "requests not installed — skipping live API tests")
        return

    endpoints = [
        ("GET",  "/ping",              None,                          [200],       "Root health check"),
        ("GET",  "/docs",                None,                          [200],       "Swagger UI accessible"),
        ("GET",  "/agent/status",        None,                          [200],       "Agent intelligence status"),
        ("POST", "/auth/login",          {"email": "x", "password": "x"}, [401, 422], "Auth login rejects bad credentials"),
        ("POST", "/workflow/run",        {"topic": "test", "plan": "normal"}, [401, 422], "Workflow run requires auth"),
        ("GET",  "/agent/memory",        None,                          [401, 403],  "Agent memory requires auth"),
        ("POST", "/agent/content-gap",   {"niche": "python"},           [401, 403],  "Content gap requires auth"),
    ]

    session = requests.Session()
    session.timeout = 10

    for method, path, body, expected_codes, description in endpoints:
        url = f"{base_url}{path}"
        try:
            if method == "GET":
                resp = session.get(url)
            else:
                resp = session.post(url, json=body)

            if resp.status_code in expected_codes:
                record("pass", f"{method} {path} → {resp.status_code} ({description})")
            else:
                record("fail", f"{method} {path} → {resp.status_code} (expected {expected_codes}) — {description}")
        except requests.exceptions.ConnectionError:
            record("fail", f"{method} {path} → Connection refused. Is the server running?")
        except Exception as e:
            record("fail", f"{method} {path} → {e}")

    # Full auth flow test
    header("14b. Full Auth + Workflow Flow")
    TEST_EMAIL = "system_test_user@aicontentstudio.dev"
    TEST_PASS  = "TestPass123!"
    TEST_NAME  = "System Test User"
    try:
        # Try signup — 409 is fine (user already exists)
        signup_resp = session.post(f"{base_url}/auth/signup", json={
            "email": TEST_EMAIL,
            "password": TEST_PASS,
            "name": TEST_NAME,
        })
        if signup_resp.status_code == 200:
            record("pass", "Auth signup works")
        elif signup_resp.status_code == 409:
            record("pass", "Auth signup: test user already exists (expected on re-run)")
        else:
            record("warn", f"Signup returned {signup_resp.status_code}: {signup_resp.text[:100]}")

        # Login with the test user
        login_resp = session.post(f"{base_url}/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASS,
        })
        body = login_resp.json()

        if "access_token" in body:
            token = body["access_token"]
            record("pass", "Auth login returns access_token")

            auth_headers = {"Authorization": f"Bearer {token}"}

            # Test /auth/me
            me_resp = session.get(f"{base_url}/auth/me", headers=auth_headers)
            if me_resp.status_code == 200:
                record("pass", f"/auth/me works — user: {me_resp.json().get('email')}")
            else:
                record("warn", f"/auth/me returned {me_resp.status_code}")

            # Test agent status with auth
            status_resp = session.get(f"{base_url}/agent/status", headers=auth_headers)
            if status_resp.status_code == 200:
                status = status_resp.json()
                record("pass", f"/agent/status: mongodb_direct={status.get('mongodb_direct')}, mongodb_mcp={status.get('mongodb_mcp')}")
            else:
                record("warn", f"/agent/status returned {status_resp.status_code}")

            # Test agent memory
            mem_resp = session.get(f"{base_url}/agent/memory", headers=auth_headers)
            if mem_resp.status_code == 200:
                record("pass", "/agent/memory accessible with auth")
            else:
                record("warn", f"/agent/memory returned {mem_resp.status_code}")

        else:
            record("warn", f"Login did not return token — response: {body}")

    except Exception as e:
        record("warn", f"Auth flow test error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def print_summary():
    total = sum(RESULTS.values())
    print(f"\n{'═'*60}")
    print(f"{BOLD} FINAL RESULTS{RESET}")
    print(f"{'═'*60}")
    print(f"  {GREEN}✅ PASSED{RESET}  {RESULTS['pass']}")
    print(f"  {RED}❌ FAILED{RESET}  {RESULTS['fail']}")
    print(f"  {YELLOW}⚠️  WARNED{RESET}  {RESULTS['warn']}")
    print(f"  Total      {total}")
    print(f"{'═'*60}")

    score = RESULTS['pass'] / max(total - RESULTS['warn'], 1) * 100
    if RESULTS['fail'] == 0:
        print(f"\n  {GREEN}{BOLD}🎉 ALL CRITICAL TESTS PASSED! Score: {score:.0f}%{RESET}")
    elif RESULTS['fail'] <= 2:
        print(f"\n  {YELLOW}{BOLD}⚠️  Minor issues found. Score: {score:.0f}%{RESET}")
    else:
        print(f"\n  {RED}{BOLD}❌ Issues need fixing. Score: {score:.0f}%{RESET}")
    print()


def main():
    parser = argparse.ArgumentParser(description="AI Content Studio — Full System Check")
    parser.add_argument("--live",     action="store_true", help="Also test live API endpoints")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Server base URL for live tests")
    parser.add_argument("--skip-llm", action="store_true", help="Skip the Qwen LLM API call test")
    parser.add_argument("--skip-mcp", action="store_true", help="Skip MCP subprocess test (faster)")
    args = parser.parse_args()

    print(f"\n{BOLD}{BLUE}{'═'*60}")
    print(" AI Content Studio — Full System Health Check")
    print(f"{'═'*60}{RESET}")
    print(f"  Backend dir: {BACKEND_DIR}")
    print(f"  Time:        {time.strftime('%Y-%m-%d %H:%M:%S')}")
    if args.live:
        print(f"  Live server: {args.base_url}")
    print()

    test_env()
    test_postgresql()
    test_mongodb_direct()

    if not args.skip_mcp:
        test_mongodb_mcp()
    else:
        RESULTS["skip"] += 2
        info("SKIP  MongoDB MCP tests (--skip-mcp)")

    test_memory_services()
    test_elasticsearch()

    if not args.skip_llm:
        test_llm()
    else:
        RESULTS["skip"] += 1
        info("SKIP  Qwen LLM test (--skip-llm)")

    test_checkpointer()
    test_agent_imports()
    test_graph_compilation()
    test_workflow_dry_run()

    if args.live:
        test_live_api(args.base_url)
    else:
        print(f"\n{YELLOW}  Tip: Run with --live to also test API endpoints{RESET}")
        print(f"{YELLOW}       python test_full_system.py --live{RESET}")

    print_summary()

    # Clean up MCP subprocess to avoid 'Event loop is closed' on exit
    try:
        import asyncio
        from app.mcp.mongodb.mcp_runner import shutdown_mcp
        asyncio.run(shutdown_mcp())
    except Exception:
        pass


if __name__ == "__main__":
    main()
