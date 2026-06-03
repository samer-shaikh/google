"""
Verifies:
  1. /workflow/run  — research runs, graph pauses at HITL
  2. /workflow/resume — all 4 remaining agents run (ideas, script, thumbnail, seo)
  3. /workflow/optimize-upload — upload optimizer runs as separate workflow

Usage:
  Terminal 1:  uvicorn app.main:app    (NO --reload, keeps MemorySaver alive)
  Terminal 2:  python test_workflow.py
"""

import requests

BASE  = "http://127.0.0.1:8000"
TOPIC = "How AI Agents can automate businesses"

def check(label, value):
    ok      = bool(value and len(str(value).strip()) > 30)
    status  = "PASS" if ok else "FAIL"
    preview = str(value)[:90].replace("\n", " ") if value else "EMPTY"
    print(f"  [{status}] {label}: {preview}")
    return ok

# ── Step 1: Start ──────────────────────────────────────────────────
print("\n── STEP 1: POST /workflow/run ─────────────────────────────")
r = requests.post(f"{BASE}/workflow/run", json={"topic": TOPIC, "plan": "normal"})
assert r.status_code == 200, f"HTTP {r.status_code}\n{r.text}"
data = r.json()

print(f"  status   : {data['status']}")
print(f"  thread_id: {data['thread_id']}")
print(f"  paused_at: {data.get('paused_at')}")

assert data["status"] == "awaiting_approval", \
    f"ERROR: expected 'awaiting_approval', got '{data['status']}'. Graph did not pause."

check("research", data["research"])
thread_id = data["thread_id"]

# ── Step 2: Resume ─────────────────────────────────────────────────
print("\n── STEP 2: POST /workflow/resume (approved=true) ──────────")
r2 = requests.post(f"{BASE}/workflow/resume", json={
    "thread_id": thread_id,
    "approved": True
})
assert r2.status_code == 200, f"HTTP {r2.status_code}\n{r2.text}"
result = r2.json()

print(f"  status: {result['status']}")
assert result["status"] == "completed", \
    f"ERROR: expected 'completed', got '{result['status']}'"

print("\n── STEP 3: Verify all nodes produced output ───────────────")
passes = [
    check("research",  result.get("research")),
    check("ideas",     result.get("ideas")),
    check("script",    result.get("script")),
    check("thumbnail", result.get("thumbnail")),
    check("seo",       result.get("seo")),
]

# ── Step 3: Upload Optimizer (separate) ───────────────────────────
print("\n── STEP 4: POST /workflow/optimize-upload (separate) ──────")
r3 = requests.post(f"{BASE}/workflow/optimize-upload", json={
    "topic":  result.get("topic", TOPIC),
    "script": result.get("script", ""),
    "seo":    result.get("seo", ""),
    "plan":   "normal"
})
assert r3.status_code == 200, f"HTTP {r3.status_code}\n{r3.text}"
upload_result = r3.json()
passes.append(check("upload", upload_result.get("upload")))

print(f"\n{'─'*50}")
if all(passes):
    print("ALL CHECKS PASSED. Full workflow is working correctly.")
else:
    failed = [["research","ideas","script","thumbnail","seo","upload"][i]
              for i, p in enumerate(passes) if not p]
    print(f"FAILED: {', '.join(failed)}")
    print("Check the server terminal for traceback details.")
print(f"{'─'*50}\n")
