"""
test_upload.py
==============
End-to-end upload test for AI Content Studio.

Tests the complete flow:
  1. Login
  2. Check YouTube is connected
  3. Run content generation workflow
  4. Approve research
  5. Select idea
  6. Start upload workflow (generates SEO)
  7. Approve + upload to YouTube

Usage:
  # Demo mode (no real video file — tests everything except actual upload):
  python test_upload.py

  # Real upload mode (provide a real .mp4 file):
  python test_upload.py --video "C:/path/to/your/video.mp4"

  # With thumbnail:
  python test_upload.py --video "C:/path/to/video.mp4" --thumbnail "C:/path/to/thumb.jpg"
"""

import requests
import argparse
import time
import sys

BASE_URL = "http://127.0.0.1:8000"

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg):   print(f"  {GREEN}✅{RESET} {msg}")
def fail(msg): print(f"  {RED}❌{RESET} {msg}"); sys.exit(1)
def info(msg): print(f"  {BLUE}ℹ️ {RESET} {msg}")
def warn(msg): print(f"  {YELLOW}⚠️ {RESET} {msg}")
def step(msg): print(f"\n{BOLD}{BLUE}── {msg}{RESET}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--email",     default="system_test_user@aicontentstudio.dev")
    parser.add_argument("--password",  default="TestPass123!")
    parser.add_argument("--topic",     default="How to learn Python in 30 days")
    parser.add_argument("--video",     default="", help="Absolute path to .mp4 file for real upload")
    parser.add_argument("--thumbnail", default="", help="Absolute path to .jpg thumbnail (optional)")
    args = parser.parse_args()

    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})

    # ── Step 1: Login ─────────────────────────────────────────────
    step("Step 1: Login")
    r = s.post(f"{BASE_URL}/auth/login", json={
        "email": args.email, "password": args.password
    })
    if r.status_code != 200:
        fail(f"Login failed ({r.status_code}): {r.text}")

    token = r.json().get("access_token")
    user  = r.json().get("user", {})
    s.headers.update({"Authorization": f"Bearer {token}"})
    ok(f"Logged in as {user.get('email')} (id={user.get('id')})")

    # ── Step 2: Check YouTube ─────────────────────────────────────
    step("Step 2: Check YouTube Connection")
    r = s.get(f"{BASE_URL}/youtube/me")
    yt = r.json()
    if yt.get("connected"):
        ok(f"YouTube connected — channel: {yt.get('channel_name')} ({yt.get('channel_id')})")
    else:
        warn("YouTube not connected — upload will run in demo mode")
        warn("To connect: GET /youtube/connect → open auth_url in browser")
        if args.video:
            fail("Cannot do real upload without YouTube connected. Connect first.")

    # ── Step 3: Check creator profile ────────────────────────────
    step("Step 3: Check Creator Profile")
    r = s.get(f"{BASE_URL}/creator-profile/me")
    if r.status_code == 200:
        profile = r.json()
        ok(f"Creator profile found — niche: {profile.get('topics', {}).get('creator_niche', 'unknown')}")
    else:
        warn("No creator profile yet — workflow will use defaults")

    # ── Step 4: Run content workflow ──────────────────────────────
    step("Step 4: Start Content Generation")
    info(f"Topic: {args.topic}")
    info("Running research (10-20s)...")

    r = s.post(f"{BASE_URL}/workflow/run", json={
        "topic": args.topic,
        "plan": "normal"
    })
    if r.status_code != 200:
        fail(f"workflow/run failed ({r.status_code}): {r.text}")

    data = r.json()
    thread_id     = data["thread_id"]
    generation_id = data["generation_id"]
    research      = data.get("research", "")

    ok(f"Research complete — thread_id: {thread_id}")
    ok(f"Generation ID: {generation_id}")
    info(f"Research preview: {research[:150]}...")

    # ── Step 5: Approve research ──────────────────────────────────
    step("Step 5: Approve Research")
    r = s.post(f"{BASE_URL}/workflow/resume", json={
        "thread_id": thread_id,
        "approved": True
    })
    if r.status_code != 200:
        fail(f"workflow/resume failed ({r.status_code}): {r.text}")

    data  = r.json()
    ideas = data.get("ideas", [])
    ok(f"Got {len(ideas)} ideas:")
    for i, idea in enumerate(ideas, 1):
        print(f"    {i}. {idea}")

    # ── Step 6: Select idea ───────────────────────────────────────
    step("Step 6: Select Idea (picking #1 automatically)")
    selected_idea = ideas[0] if ideas else args.topic
    info(f"Selected: {selected_idea}")
    info("Generating script + thumbnail (15-30s)...")

    r = s.post(f"{BASE_URL}/workflow/select-idea", json={
        "thread_id": thread_id,
        "selected_idea": selected_idea
    })
    if r.status_code != 200:
        fail(f"workflow/select-idea failed ({r.status_code}): {r.text}")

    data      = r.json()
    script    = data.get("script", "")
    thumbnail = data.get("thumbnail", "")

    ok(f"Script generated — {len(script)} characters")
    ok(f"Thumbnail description — {len(thumbnail)} characters")
    info(f"Script preview: {script[:200]}...")

    # ── Step 7: Start upload workflow ─────────────────────────────
    step("Step 7: Start Upload Workflow (SEO Generation)")
    info("Generating SEO title, description, tags (10-15s)...")

    upload_body = {
        "generation_id":  generation_id,
        "privacy_status": "private",
        "plan":           "normal"
    }
    if args.video:
        upload_body["video_file_path"] = args.video
        info(f"Video file: {args.video}")
    else:
        info("No video file — running in DEMO MODE (metadata only, no real upload)")

    if args.thumbnail:
        upload_body["thumbnail_file_path"] = args.thumbnail
        info(f"Thumbnail file: {args.thumbnail}")

    r = s.post(f"{BASE_URL}/workflow/upload/start", json=upload_body)
    if r.status_code != 200:
        fail(f"workflow/upload/start failed ({r.status_code}): {r.text}")

    data           = r.json()
    upload_thread  = data["thread_id"]
    seo_title      = data.get("seo_title", "")
    seo_description= data.get("seo_description", "")
    seo_tags       = data.get("seo_tags", [])
    seo_hashtags   = data.get("seo_hashtags", [])
    seo_category   = data.get("seo_category", "")

    ok(f"SEO generated — upload thread_id: {upload_thread}")
    print(f"\n  {BOLD}Generated SEO:{RESET}")
    print(f"  Title:    {seo_title}")
    print(f"  Category: {seo_category}")
    print(f"  Tags:     {', '.join(seo_tags[:5])}...")
    print(f"  Hashtags: {' '.join(seo_hashtags[:3])}")
    print(f"  Desc:     {seo_description[:150]}...")

    # ── Step 8: Approve + Upload ──────────────────────────────────
    step("Step 8: Approve SEO & Upload")
    if args.video:
        info("Uploading to YouTube... (this may take several minutes for large files)")
    else:
        info("Approving metadata (demo mode — no real upload)...")

    r = s.post(f"{BASE_URL}/workflow/upload/review", json={
        "thread_id": upload_thread,
        "approved": True
    })
    if r.status_code != 200:
        fail(f"workflow/upload/review failed ({r.status_code}): {r.text}")

    result = r.json()
    upload_status    = result.get("upload_status")
    youtube_video_id = result.get("youtube_video_id", "")
    youtube_url      = result.get("youtube_video_url", "")
    thumb_status     = result.get("thumbnail_status", "skipped")
    upload_record_id = result.get("upload_record_id")

    print(f"\n{'═'*55}")
    print(f"{BOLD} UPLOAD RESULT{RESET}")
    print(f"{'═'*55}")
    print(f"  Status:          {GREEN if upload_status in ('uploaded','metadata_ready') else RED}{upload_status}{RESET}")
    print(f"  Upload Record:   #{upload_record_id}")
    print(f"  Thumbnail:       {thumb_status}")

    if upload_status == "uploaded":
        print(f"  {GREEN}{BOLD}YouTube Video ID: {youtube_video_id}{RESET}")
        print(f"  {GREEN}{BOLD}YouTube URL:      {youtube_url}{RESET}")
        ok("Video successfully uploaded to YouTube!")
    elif upload_status == "metadata_ready":
        ok("Demo mode complete — SEO metadata saved to database")
        info("To do a real upload: run with --video flag pointing to a .mp4 file")
        info(f"Upload record #{upload_record_id} saved — check GET /workflow/uploads/{upload_record_id}")
    elif upload_status == "failed":
        error = result.get("upload_error", "unknown error")
        fail(f"Upload failed: {error}")
    print(f"{'═'*55}\n")

    # ── Summary ───────────────────────────────────────────────────
    print(f"\n{BOLD}What was created:{RESET}")
    print(f"  Generation ID:   {generation_id}")
    print(f"  Upload Record:   #{upload_record_id}")
    print(f"  SEO Title:       {seo_title}")
    print(f"  Content in DB:   GET /workflow/history/{generation_id}")
    print(f"  Upload in DB:    GET /workflow/uploads/{upload_record_id}")
    if youtube_url:
        print(f"  Live on YouTube: {youtube_url}")
    print()


if __name__ == "__main__":
    main()
