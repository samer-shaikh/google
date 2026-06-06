"""
check.py  —  AI Content Studio health checker
Run from the backend folder:
    python check.py

Checks every layer in order:
  1. Server is reachable
  2. DB tables exist
  3. Signup works
  4. Login works + returns JWT
  5. Swagger auth works (GET /auth/me with Bearer token)
  6. YouTube connect returns a real auth URL (not mock)
  7. DB model consistency (user_id types, FKs, new columns)
  8. ENV variables are all set
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
WARN = "\033[93m WARN \033[0m"
INFO = "\033[94m INFO \033[0m"

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

# ── Helpers ──────────────────────────────────────────────────────────────────

def rand_email():
    suffix = "".join(random.choices(string.ascii_lowercase, k=6))
    return f"test_{suffix}@example.com"

# ── 1. ENV variables ─────────────────────────────────────────────────────────

print("\n" + "="*55)
print("  AI Content Studio — Health Check")
print("  " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
print("="*55 + "\n")

print("[ ENV Variables ]\n")

env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    from dotenv import load_dotenv
    load_dotenv(env_path)

required_env = [
    "DATABASE_URl",
    "SECRET_KEY_FOR_LOGIN",
    "SECRET_KEY",
    "ALGORITHM",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "YOUTUBE_REDIRECT_URI",
]

for key in required_env:
    val = os.getenv(key)
    if val:
        # Show first 8 chars only for secrets
        preview = val[:8] + "..." if len(val) > 8 else val
        print(f"{PASS} {key} = {preview}")
    else:
        print(f"{FAIL} {key} is NOT SET")

# ── 2. Server reachable ───────────────────────────────────────────────────────

print("\n[ Server ]\n")

def check_server():
    r = requests.get(f"{BASE}/docs", timeout=5)
    assert r.status_code == 200, f"Docs returned {r.status_code}"
    return "Swagger UI is up"

def check_openapi():
    r = requests.get(f"{BASE}/openapi.json", timeout=5)
    assert r.status_code == 200, f"openapi.json returned {r.status_code}"
    schema = r.json()
    schemes = schema.get("components", {}).get("securitySchemes", {})
    assert "BearerAuth" in schemes, (
        "BearerAuth scheme missing from openapi.json — "
        "Swagger lock icon will not work"
    )
    scheme_type = schemes["BearerAuth"].get("scheme")
    assert scheme_type == "bearer", f"Expected 'bearer' scheme, got '{scheme_type}'"
    return "BearerAuth scheme present"

check("Server reachable at localhost:8000", check_server)
check("Swagger has BearerAuth scheme (not OAuth2PasswordBearer)", check_openapi)

# ── 3. Auth flow ──────────────────────────────────────────────────────────────

print("\n[ Auth Flow ]\n")

TEST_EMAIL = rand_email()
TEST_PASS = "TestPass123!"
access_token = None

def check_signup():
    r = requests.post(f"{BASE}/auth/signup", json={
        "email": TEST_EMAIL,
        "password": TEST_PASS,
        "name": "Test User"
    }, timeout=5)
    assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
    body = r.json()
    assert "error" not in body, f"Signup error: {body.get('error')}"
    return f"Created {TEST_EMAIL}"

def check_login():
    global access_token
    r = requests.post(f"{BASE}/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASS
    }, timeout=5)
    assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
    body = r.json()
    assert "error" not in body, f"Login error: {body.get('error')}"
    assert "access_token" in body, "No access_token in response"
    assert "refresh_token" in body, "No refresh_token in response"
    access_token = body["access_token"]
    return f"Got token: {access_token[:20]}..."

def check_bearer_auth():
    assert access_token, "No access_token — login must pass first"
    r = requests.get(
        f"{BASE}/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=5
    )
    assert r.status_code == 200, (
        f"Status {r.status_code}: {r.text}\n"
        "  → This means the Bearer token is not being read correctly"
    )
    body = r.json()
    assert body.get("email") == TEST_EMAIL, f"Wrong user returned: {body}"
    return f"Authenticated as {body['email']}"

def check_no_token_rejected():
    r = requests.get(f"{BASE}/auth/me", timeout=5)
    assert r.status_code == 401, (
        f"Expected 401 without token, got {r.status_code} — "
        "routes are not protected"
    )
    return "Unauthenticated request correctly rejected"

def check_bad_token_rejected():
    r = requests.get(
        f"{BASE}/auth/me",
        headers={"Authorization": "Bearer fake.token.here"},
        timeout=5
    )
    assert r.status_code == 401, (
        f"Expected 401 for bad token, got {r.status_code}"
    )
    return "Invalid token correctly rejected"

def check_refresh():
    # Login fresh to get refresh token
    r = requests.post(f"{BASE}/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASS
    }, timeout=5)
    refresh = r.json().get("refresh_token")
    assert refresh, "No refresh_token from login"

    r2 = requests.post(f"{BASE}/auth/refresh", json={
        "refresh_token": refresh
    }, timeout=5)
    assert r2.status_code == 200, f"Refresh failed: {r2.text}"
    body = r2.json()
    assert "access_token" in body, "No access_token in refresh response"
    return "Refresh token exchange works"

check("Signup",                    check_signup)
check("Login returns JWT",         check_login)
check("Bearer token auth works",   check_bearer_auth)
check("No token → 401",            check_no_token_rejected)
check("Bad token → 401",           check_bad_token_rejected)
check("Refresh token exchange",    check_refresh)

# ── 4. YouTube OAuth URL ──────────────────────────────────────────────────────

print("\n[ YouTube OAuth ]\n")

def check_youtube_connect():
    assert access_token, "Need access_token from login"
    r = requests.get(
        f"{BASE}/youtube/connect",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=5
    )
    assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
    body = r.json()
    assert "auth_url" in body, f"No auth_url in response: {body}"
    url = body["auth_url"]
    assert "accounts.google.com" in url, f"URL doesn't look like Google OAuth: {url}"
    assert "youtube" in url.lower() or "googleapis" in url.lower(), (
        f"URL doesn't contain YouTube scope: {url}"
    )
    assert "offline" in url, "access_type=offline missing — won't get refresh token"
    assert "consent" in url, "prompt=consent missing — may not get refresh token on re-auth"
    return f"Auth URL generated: {url[:60]}..."

def check_youtube_me_not_connected():
    assert access_token, "Need access_token"
    r = requests.get(
        f"{BASE}/youtube/me",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=5
    )
    assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
    body = r.json()
    # For a fresh test user, connected should be False
    assert "connected" in body, f"No 'connected' field in response: {body}"
    return f"connected={body['connected']}"

check("YouTube /connect returns Google OAuth URL",  check_youtube_connect)
check("YouTube /me returns connected status",       check_youtube_me_not_connected)

# ── 5. DB column check ────────────────────────────────────────────────────────

print("\n[ Database Schema ]\n")

def check_db_schema():
    try:
        from sqlalchemy import create_engine, inspect, text
        from dotenv import load_dotenv
        load_dotenv(env_path)

        db_url = os.getenv("DATABASE_URl") or os.getenv("DATABASE_URL")
        assert db_url, "DATABASE_URl env var not set"

        engine = create_engine(db_url)
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        return tables

    except Exception as e:
        raise AssertionError(str(e))

def check_tables_exist():
    from sqlalchemy import create_engine, inspect
    db_url = os.getenv("DATABASE_URl") or os.getenv("DATABASE_URL")
    engine = create_engine(db_url)
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())

    required = {"users", "youtube_accounts", "youtube_videos", "creator_profiles"}
    missing = required - existing
    assert not missing, f"Missing tables: {missing}"
    return f"All required tables exist: {required}"

def check_creator_profile_columns():
    from sqlalchemy import create_engine, inspect
    db_url = os.getenv("DATABASE_URl") or os.getenv("DATABASE_URL")
    engine = create_engine(db_url)
    inspector = inspect(engine)

    cols = {c["name"]: c for c in inspector.get_columns("creator_profiles")}

    # user_id must be Integer (was String before the fix)
    assert "user_id" in cols, "creator_profiles.user_id column missing"
    uid_type = str(cols["user_id"]["type"]).upper()
    assert "INT" in uid_type, (
        f"creator_profiles.user_id is {uid_type} — must be INTEGER "
        f"(run 'alembic revision --autogenerate' and migrate)"
    )

    # New columns we added
    for col in ["created_at", "updated_at", "prompt_version", "videos_analyzed"]:
        assert col in cols, (
            f"creator_profiles.{col} column missing — "
            f"DB schema is out of sync with model. "
            f"Drop and recreate the table or run a migration."
        )
    return "creator_profiles schema is correct"

def check_youtube_video_columns():
    from sqlalchemy import create_engine, inspect
    db_url = os.getenv("DATABASE_URl") or os.getenv("DATABASE_URL")
    engine = create_engine(db_url)
    inspector = inspect(engine)

    cols = {c["name"] for c in inspector.get_columns("youtube_videos")}

    for col in ["fetched_at", "is_analyzed", "video_id"]:
        assert col in cols, (
            f"youtube_videos.{col} missing — "
            f"DB schema is out of sync with model"
        )

    # Check unique constraint on video_id
    uq = inspector.get_unique_constraints("youtube_videos")
    uq_cols = [c for u in uq for c in u["column_names"]]
    indexes = inspector.get_indexes("youtube_videos")
    idx_cols = [c for i in indexes for c in i["column_names"] if i.get("unique")]
    all_unique = set(uq_cols + idx_cols)
    assert "video_id" in all_unique, (
        "youtube_videos.video_id has no UNIQUE constraint — "
        "duplicate rows will be inserted on re-fetch"
    )
    return "youtube_videos schema is correct"

def check_youtube_account_columns():
    from sqlalchemy import create_engine, inspect
    db_url = os.getenv("DATABASE_URl") or os.getenv("DATABASE_URL")
    engine = create_engine(db_url)
    inspector = inspect(engine)

    cols = {c["name"] for c in inspector.get_columns("youtube_accounts")}
    for col in ["token_expiry", "created_at", "updated_at", "channel_id", "channel_name"]:
        assert col in cols, (
            f"youtube_accounts.{col} missing — DB schema out of sync with model"
        )
    return "youtube_accounts schema is correct"

check("Required DB tables exist",            check_tables_exist)
check("creator_profiles schema is correct",  check_creator_profile_columns)
check("youtube_videos schema is correct",    check_youtube_video_columns)
check("youtube_accounts schema is correct",  check_youtube_account_columns)

# ── 6. Creator profile route ──────────────────────────────────────────────────

print("\n[ Creator Profile Routes ]\n")

def check_profile_me_404():
    assert access_token, "Need access_token"
    r = requests.get(
        f"{BASE}/creator-profile/me",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=5
    )
    # Fresh user has no profile yet — should be 404, not 500
    assert r.status_code == 404, (
        f"Expected 404 for user with no profile, got {r.status_code}: {r.text}"
    )
    return "Returns 404 correctly when no profile exists"

check("GET /creator-profile/me → 404 for new user", check_profile_me_404)

# ── Summary ───────────────────────────────────────────────────────────────────

print("\n" + "="*55)
passed = sum(1 for _, ok, _ in results if ok)
failed = sum(1 for _, ok, _ in results if not ok)
print(f"  Results: {passed} passed, {failed} failed out of {len(results)} checks")
print("="*55)

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
