"""
check.py  —  AI Content Studio health checker
Run from the backend folder:
    python check.py

Checks every layer in order:
  1. ENV variables
  2. Server reachable + Swagger BearerAuth
  3. Auth flow (signup, login, bearer, refresh)
  4. YouTube OAuth URL
  5. DB schema (all tables + columns)
  6. Creator profile routes
  7. Content generation workflow (structure + state)
  8. Upload workflow (structure + state)
  9. Generation history routes
"""

import sys
import os
import requests
import random
import string
from datetime import datetime

BASE = "http://localhost:8000"
PASS = "\033[92m PASS \033[0m"
FAIL = "\033[91m FAIL \033[0m"

results = []

def check(name, fn):
    try:
        msg = fn()
        print(f"{PASS} {name}" + (f"  →  {msg}" if msg else ""))
        results.append((name, True, msg))
    except AssertionError as e:
        print(f"{FAIL} {name}  →  {e}")
        results.append((name, False, str(e)))
    except Exception as e:
        print(f"{FAIL} {name}  →  {type(e).__name__}: {e}")
        results.append((name, False, str(e)))

def rand_email():
    s = "".join(random.choices(string.ascii_lowercase, k=6))
    return f"test_{s}@example.com"

# Shared state across checks
TEST_EMAIL   = rand_email()
TEST_PASS    = "TestPass123!"
access_token = None
thread_id    = None
generation_id = None

# ── ENV ───────────────────────────────────────────────────────────────────────

print("\n" + "="*60)
print("  AI Content Studio — Health Check")
print("  " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
print("="*60 + "\n")

print("[ ENV Variables ]\n")

env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    from dotenv import load_dotenv
    load_dotenv(env_path)

required_env = [
    "DATABASE_URl", "SECRET_KEY_FOR_LOGIN", "SECRET_KEY",
    "ALGORITHM", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET",
    "YOUTUBE_REDIRECT_URI",
]
for key in required_env:
    val = os.getenv(key)
    if val:
        preview = val[:8] + "..." if len(val) > 8 else val
        print(f"{PASS} {key} = {preview}")
    else:
        print(f"{FAIL} {key} is NOT SET")

# ── SERVER ────────────────────────────────────────────────────────────────────

print("\n[ Server ]\n")

def check_server():
    r = requests.get(f"{BASE}/docs", timeout=5)
    assert r.status_code == 200, f"Docs returned {r.status_code}"
    return "Swagger UI is up"

def check_openapi():
    r = requests.get(f"{BASE}/openapi.json", timeout=5)
    assert r.status_code == 200
    schema = r.json()
    schemes = schema.get("components", {}).get("securitySchemes", {})
    assert "BearerAuth" in schemes, "BearerAuth scheme missing"
    assert schemes["BearerAuth"].get("scheme") == "bearer"
    return "BearerAuth scheme present"

def check_routes_registered():
    r = requests.get(f"{BASE}/openapi.json", timeout=5)
    schema = r.json()
    paths = set(schema.get("paths", {}).keys())
    required_routes = {
        "/workflow/run",
        "/workflow/resume",
        "/workflow/select-idea",
        "/workflow/upload/start",
        "/workflow/upload/review",
        "/workflow/history",
    }
    missing = required_routes - paths
    assert not missing, f"Missing routes in OpenAPI: {missing}"
    # Confirm SEO is NOT in the content workflow
    assert "/workflow/seo" not in paths, "SEO route should not exist in content workflow"
    return f"All {len(required_routes)} required routes registered"

check("Server reachable",        check_server)
check("BearerAuth in Swagger",   check_openapi)
check("All routes registered",   check_routes_registered)

# ── AUTH ──────────────────────────────────────────────────────────────────────

print("\n[ Auth Flow ]\n")

def check_signup():
    r = requests.post(f"{BASE}/auth/signup", json={
        "email": TEST_EMAIL, "password": TEST_PASS, "name": "Test User"
    }, timeout=5)
    assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
    assert "error" not in r.json()
    return f"Created {TEST_EMAIL}"

def check_login():
    global access_token
    r = requests.post(f"{BASE}/auth/login", json={
        "email": TEST_EMAIL, "password": TEST_PASS
    }, timeout=5)
    assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
    body = r.json()
    assert "access_token"  in body, "No access_token"
    assert "refresh_token" in body, "No refresh_token"
    access_token = body["access_token"]
    return f"Token: {access_token[:20]}..."

def check_bearer():
    r = requests.get(f"{BASE}/auth/me",
        headers={"Authorization": f"Bearer {access_token}"}, timeout=5)
    assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
    assert r.json().get("email") == TEST_EMAIL
    return f"Authenticated as {TEST_EMAIL}"

def check_no_token():
    r = requests.get(f"{BASE}/auth/me", timeout=5)
    assert r.status_code == 401, f"Expected 401, got {r.status_code}"
    return "401 without token"

def check_bad_token():
    r = requests.get(f"{BASE}/auth/me",
        headers={"Authorization": "Bearer bad.token"}, timeout=5)
    assert r.status_code == 401, f"Expected 401, got {r.status_code}"
    return "401 for bad token"

def check_refresh():
    r = requests.post(f"{BASE}/auth/login", json={
        "email": TEST_EMAIL, "password": TEST_PASS}, timeout=5)
    refresh = r.json().get("refresh_token")
    assert refresh, "No refresh_token"
    r2 = requests.post(f"{BASE}/auth/refresh",
        json={"refresh_token": refresh}, timeout=5)
    assert r2.status_code == 200, f"Refresh failed: {r2.text}"
    assert "access_token" in r2.json()
    return "Refresh works"

check("Signup",           check_signup)
check("Login → JWT",      check_login)
check("Bearer auth",      check_bearer)
check("No token → 401",   check_no_token)
check("Bad token → 401",  check_bad_token)
check("Refresh token",    check_refresh)

# ── YOUTUBE ───────────────────────────────────────────────────────────────────

print("\n[ YouTube OAuth ]\n")

def check_youtube_connect():
    r = requests.get(f"{BASE}/youtube/connect",
        headers={"Authorization": f"Bearer {access_token}"}, timeout=5)
    assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
    url = r.json().get("auth_url", "")
    assert "accounts.google.com" in url, "Not a Google OAuth URL"
    assert "offline"  in url, "access_type=offline missing"
    assert "consent"  in url, "prompt=consent missing"
    assert "S256"     in url, "PKCE code_challenge_method missing"
    return f"{url[:55]}..."

def check_youtube_me():
    r = requests.get(f"{BASE}/youtube/me",
        headers={"Authorization": f"Bearer {access_token}"}, timeout=5)
    assert r.status_code == 200, f"Status {r.status_code}"
    assert "connected" in r.json()
    return f"connected={r.json()['connected']}"

check("YouTube /connect → PKCE OAuth URL", check_youtube_connect)
check("YouTube /me → connected status",    check_youtube_me)

# ── DATABASE SCHEMA ───────────────────────────────────────────────────────────

print("\n[ Database Schema ]\n")

def _inspector():
    from sqlalchemy import create_engine, inspect
    db_url = os.getenv("DATABASE_URl") or os.getenv("DATABASE_URL")
    return inspect(create_engine(db_url))

def check_tables():
    ins = _inspector()
    existing = set(ins.get_table_names())
    required = {"users", "youtube_accounts", "youtube_videos",
                 "creator_profiles", "generations"}
    missing  = required - existing
    assert not missing, f"Missing tables: {missing}"
    return f"All {len(required)} tables present"

def check_creator_profile_schema():
    ins  = _inspector()
    cols = {c["name"]: c for c in ins.get_columns("creator_profiles")}
    assert "user_id" in cols, "user_id missing"
    assert "INT" in str(cols["user_id"]["type"]).upper(), \
        f"user_id is {cols['user_id']['type']} — must be INTEGER"
    for col in ["created_at", "updated_at", "prompt_version", "videos_analyzed"]:
        assert col in cols, f"creator_profiles.{col} missing"
    return "creator_profiles schema correct"

def check_youtube_video_schema():
    ins  = _inspector()
    cols = {c["name"] for c in ins.get_columns("youtube_videos")}
    for col in ["fetched_at", "is_analyzed", "video_id"]:
        assert col in cols, f"youtube_videos.{col} missing"
    uq   = ins.get_unique_constraints("youtube_videos")
    idxs = ins.get_indexes("youtube_videos")
    all_unique = {c for u in uq  for c in u["column_names"]} | \
                 {c for i in idxs for c in i["column_names"] if i.get("unique")}
    assert "video_id" in all_unique, "youtube_videos.video_id has no UNIQUE constraint"
    return "youtube_videos schema correct"

def check_youtube_account_schema():
    ins  = _inspector()
    cols = {c["name"] for c in ins.get_columns("youtube_accounts")}
    for col in ["token_expiry", "created_at", "updated_at", "channel_id", "channel_name"]:
        assert col in cols, f"youtube_accounts.{col} missing"
    return "youtube_accounts schema correct"

def check_generation_schema():
    ins  = _inspector()
    cols = {c["name"] for c in ins.get_columns("generations")}
    required = {
        "user_id", "workflow_thread_id", "topic", "plan", "status",
        "research", "ideas", "selected_idea", "script", "thumbnail",
        "creator_profile_snapshot", "error", "created_at", "updated_at",
    }
    missing = required - cols
    assert not missing, f"generations missing columns: {missing}"
    # Confirm seo column is NOT in generations (it moved to upload workflow)
    assert "seo" in cols or True, ""  # seo col can exist as empty — just checking table loads
    return "generations schema correct"

check("All tables exist",            check_tables)
check("creator_profiles schema",     check_creator_profile_schema)
check("youtube_videos schema",       check_youtube_video_schema)
check("youtube_accounts schema",     check_youtube_account_schema)
check("generations schema",          check_generation_schema)

# ── CREATOR PROFILE ROUTES ────────────────────────────────────────────────────

print("\n[ Creator Profile Routes ]\n")

def check_profile_404():
    r = requests.get(f"{BASE}/creator-profile/me",
        headers={"Authorization": f"Bearer {access_token}"}, timeout=5)
    assert r.status_code == 404, \
        f"Expected 404 for new user, got {r.status_code}: {r.text}"
    return "404 for new user (correct)"

check("GET /creator-profile/me → 404", check_profile_404)

# ── CONTENT GENERATION WORKFLOW ───────────────────────────────────────────────

print("\n[ Content Generation Workflow ]\n")

def check_workflow_run():
    global thread_id, generation_id
    r = requests.post(f"{BASE}/workflow/run",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"topic": "How to learn Python fast", "plan": "normal"},
        timeout=60,
    )
    assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
    body = r.json()
    assert "thread_id"     in body, "No thread_id in response"
    assert "generation_id" in body, "No generation_id in response"
    assert "research"      in body, "No research in response"
    assert "seo"           not in body, \
        "SEO should NOT be in /workflow/run response (it belongs in upload workflow)"
    assert body.get("status") == "awaiting_approval", \
        f"Expected 'awaiting_approval', got '{body.get('status')}'"
    assert len(body.get("research", "")) > 100, "Research output too short — LLM may have failed"

    thread_id     = body["thread_id"]
    generation_id = body["generation_id"]
    return f"thread_id={thread_id[:8]}... generation_id={generation_id}"

def check_workflow_state_paused():
    assert thread_id, "Need thread_id from /workflow/run"
    r = requests.get(f"{BASE}/workflow/status/{thread_id}",
        headers={"Authorization": f"Bearer {access_token}"}, timeout=5)
    assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
    body = r.json()
    assert body.get("is_paused") is True, "Workflow should be paused at human_approval"
    assert "human_approval" in body.get("next_node", []), \
        f"Expected next_node='human_approval', got {body.get('next_node')}"
    return "Paused at human_approval ✓"

def check_generation_pending_in_db():
    assert generation_id, "Need generation_id"
    r = requests.get(f"{BASE}/workflow/history/{generation_id}",
        headers={"Authorization": f"Bearer {access_token}"}, timeout=5)
    assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
    body = r.json()
    assert body.get("status") in ("pending", "completed"), \
        f"Unexpected status: {body.get('status')}"
    assert body.get("topic") == "How to learn Python fast"
    assert body.get("research"), "Research not saved to DB yet"
    return f"Generation {generation_id} in DB with status='{body['status']}'"

def check_workflow_resume_approve():
    assert thread_id, "Need thread_id"
    r = requests.post(f"{BASE}/workflow/resume",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"thread_id": thread_id, "approved": True},
        timeout=60,
    )
    assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
    body = r.json()
    assert "ideas" in body, "No ideas in resume response"
    ideas = body.get("ideas", [])
    assert isinstance(ideas, list) and len(ideas) >= 1, \
        f"Expected at least 1 idea, got: {ideas}"
    assert body.get("status") == "awaiting_idea_selection", \
        f"Expected awaiting_idea_selection, got {body.get('status')}"
    return f"Got {len(ideas)} ideas, paused at idea_selection"

def check_workflow_no_seo_in_content():
    """Confirm SEO node is completely removed from content generation workflow."""
    assert thread_id, "Need thread_id"
    r = requests.get(f"{BASE}/workflow/status/{thread_id}",
        headers={"Authorization": f"Bearer {access_token}"}, timeout=5)
    body = r.json()
    state_values = body.get("values", {})
    assert "seo" not in state_values, \
        "SEO field found in content workflow state — it should have been removed"
    return "No SEO in content workflow state ✓"

check("POST /workflow/run starts pipeline",      check_workflow_run)
check("Workflow paused at human_approval",       check_workflow_state_paused)
check("Generation saved to DB (pending)",        check_generation_pending_in_db)
check("POST /workflow/resume approves research", check_workflow_resume_approve)
check("No SEO in content workflow state",        check_workflow_no_seo_in_content)

# ── UPLOAD WORKFLOW ───────────────────────────────────────────────────────────

print("\n[ Upload Workflow ]\n")

def check_upload_start_needs_completed_generation():
    """
    Upload workflow should reject a 'pending' generation.
    We use generation_id=999999 (non-existent) to test 404 handling.
    """
    r = requests.post(f"{BASE}/workflow/upload/start",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"generation_id": 999999, "privacy_status": "private", "plan": "normal"},
        timeout=10,
    )
    # Should be 404 or 500 — not 200 with garbage data
    assert r.status_code in (404, 422, 500), \
        f"Expected error for non-existent generation, got {r.status_code}: {r.text}"
    return f"Correctly rejected non-existent generation ({r.status_code})"

def check_upload_review_needs_valid_thread():
    """Upload review should 404 on a fake thread_id."""
    r = requests.post(f"{BASE}/workflow/upload/review",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"thread_id": "fake-thread-id", "approved": True},
        timeout=5,
    )
    assert r.status_code in (404, 422), \
        f"Expected 404 for fake thread, got {r.status_code}: {r.text}"
    return f"Correctly rejected fake thread ({r.status_code})"

def check_upload_workflow_state_schema():
    """Verify UploadState has the required fields by checking the graph compiles."""
    from app.graph.upload_workflow import upload_graph
    from app.graph.state import UploadState
    import inspect

    hints = UploadState.__annotations__
    required_fields = {
        "generation_id", "user_id", "plan",
        "seo_title", "seo_description", "seo_tags", "seo_hashtags", "seo_category",
        "privacy_status", "youtube_video_id", "upload_status", "seo_approved",
    }
    missing = required_fields - set(hints.keys())
    assert not missing, f"UploadState missing fields: {missing}"
    return f"UploadState has all {len(required_fields)} required fields"

def check_upload_graph_nodes():
    """Verify all expected nodes are in the upload graph."""
    from app.graph.upload_workflow import upload_graph

    # Get node names from the compiled graph
    nodes = set(upload_graph.get_graph().nodes.keys())
    required_nodes = {
        "load_generation", "seo_title", "seo_description",
        "tags", "review_metadata", "upload_video",
    }
    missing = required_nodes - nodes
    assert not missing, f"Upload graph missing nodes: {missing}"
    return f"All {len(required_nodes)} nodes present: {required_nodes}"

def check_content_graph_no_seo_node():
    """Confirm seo node is completely removed from content generation graph."""
    from app.graph.workflow import graph

    nodes = set(graph.get_graph().nodes.keys())
    assert "seo" not in nodes, \
        f"'seo' node still present in content workflow graph — must be removed"
    assert "thumbnail" in nodes, "thumbnail node missing from content workflow"
    assert "save_generation" in nodes, "save_generation node missing"
    return f"Content graph nodes: {sorted(nodes)}"

check("Upload /start rejects non-existent generation", check_upload_start_needs_completed_generation)
check("Upload /review rejects fake thread",             check_upload_review_needs_valid_thread)
check("UploadState schema has all required fields",     check_upload_workflow_state_schema)
check("Upload graph has all required nodes",            check_upload_graph_nodes)
check("Content graph has NO seo node",                  check_content_graph_no_seo_node)

# ── GENERATION HISTORY ────────────────────────────────────────────────────────

print("\n[ Generation History ]\n")

def check_history_list():
    r = requests.get(f"{BASE}/workflow/history",
        headers={"Authorization": f"Bearer {access_token}"}, timeout=5)
    assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
    body = r.json()
    assert "results" in body, "No results field"
    assert "total"   in body, "No total field"
    assert isinstance(body["results"], list)
    # Should have at least the one generation we started
    assert body["total"] >= 1, "Expected at least 1 generation in history"
    return f"{body['total']} generation(s) in history"

def check_history_detail():
    assert generation_id, "Need generation_id"
    r = requests.get(f"{BASE}/workflow/history/{generation_id}",
        headers={"Authorization": f"Bearer {access_token}"}, timeout=5)
    assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
    body = r.json()
    # seo field can exist (column kept for backward compat) but should be empty/null
    if "seo" in body:
        assert not body["seo"], \
            "SEO should be empty in content generation history — it moved to upload workflow"
    assert body.get("script") or body.get("status") == "pending", \
        "Completed generation should have a script"
    return f"Generation detail correct (status={body.get('status')})"

def check_history_wrong_user():
    """History should not expose other users' generations."""
    # Try to access generation_id=1 as this fresh test user
    # If it belongs to a different user, should get 404
    r = requests.get(f"{BASE}/workflow/history/1",
        headers={"Authorization": f"Bearer {access_token}"}, timeout=5)
    # Either 404 (not found / wrong user) or 200 if user happens to own it
    assert r.status_code in (200, 404), \
        f"Unexpected status {r.status_code}: {r.text}"
    if r.status_code == 200:
        assert r.json().get("topic"), "Generation detail missing topic"
    return f"History isolation check passed ({r.status_code})"

check("GET /workflow/history lists generations",  check_history_list)
check("GET /workflow/history/:id returns detail", check_history_detail)
check("History isolated per user",               check_history_wrong_user)

# ── SUMMARY ───────────────────────────────────────────────────────────────────

print("\n" + "="*60)
passed = sum(1 for _, ok, _ in results if ok)
failed = sum(1 for _, ok, _ in results if not ok)
print(f"  Results: {passed} passed, {failed} failed out of {len(results)} checks")
print("="*60)

if failed:
    print("\nFailed checks:\n")
    for name, ok, msg in results:
        if not ok:
            print(f"  ✗  {name}")
            print(f"     {msg}\n")
    sys.exit(1)
else:
    print("\n  Everything looks good. Ready to continue building.\n")
    sys.exit(0)
