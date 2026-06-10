"""
app/jobs/trend_ingestion.py

Scheduled background job: fetch trending topics → index to Elasticsearch.
Runs once on startup for the creator's niche, then can be triggered via API.

Scheduler: uses APScheduler (add to requirements.txt if you want periodic runs).
For now, runs once at startup and is callable via POST /agent/trends/refresh.
"""
import logging
from app.agents.trend_agent import run_trend_agent_for_user, run_trend_agent

log = logging.getLogger(__name__)


def run_trend_ingestion_for_all_users() -> dict:
    """
    Run trend ingestion for all users with creator_memory documents.
    Called at startup and optionally on a schedule.
    """
    from app.mcp.elastic.client import is_elastic_enabled
    if not is_elastic_enabled():
        log.info("[trend_ingestion] Elasticsearch not configured — skipping")
        return {"skipped": True, "reason": "Elasticsearch not configured"}

    try:
        from app.mcp.mongodb.tools import find_many
        docs = find_many("creator_memory", {}, limit=100)
        if not docs:
            log.info("[trend_ingestion] No creator_memory documents found — skipping")
            return {"skipped": True, "reason": "No creators found"}

        total_indexed = 0
        for doc in docs:
            user_id = doc.get("user_id")
            niche = doc.get("profile", {}).get("niche", "")
            if not niche:
                continue
            result = run_trend_agent(niche)
            total_indexed += result.get("indexed", 0)

        log.info(f"[trend_ingestion] Completed — {total_indexed} topics indexed across {len(docs)} creators")
        return {"indexed": total_indexed, "creators": len(docs)}

    except Exception as e:
        log.warning(f"[trend_ingestion] Failed: {e}")
        return {"error": str(e)}


def seed_competitor_data(niche: str) -> int:
    """
    Seed Elasticsearch with sample competitor data for demo purposes.
    Call this when you don't have a real competitor ingestion pipeline yet.
    Returns count of documents indexed.
    """
    from app.mcp.elastic.client import get_elastic_client
    client = get_elastic_client()
    if client is None:
        return 0

    from datetime import datetime, timezone, timedelta

    SAMPLE_COMPETITORS = {
        "python": [
            {"title": "Python in 100 Seconds", "views": 2800000, "engagement_rate": 0.052, "hook_pattern": "speed-challenge", "thumbnail_style": "text-overlay"},
            {"title": "I Coded for 100 Days Straight — Here's What Happened", "views": 1500000, "engagement_rate": 0.067, "hook_pattern": "challenge-result", "thumbnail_style": "face-reaction"},
            {"title": "Python Tutorial for Absolute Beginners", "views": 4200000, "engagement_rate": 0.038, "hook_pattern": "beginner-promise", "thumbnail_style": "split-screen"},
            {"title": "Stop Writing Python Like This", "views": 980000, "engagement_rate": 0.071, "hook_pattern": "anti-pattern", "thumbnail_style": "text-only"},
            {"title": "Python FastAPI Full Course", "views": 750000, "engagement_rate": 0.055, "hook_pattern": "full-course", "thumbnail_style": "logo-text"},
        ],
        "machine learning": [
            {"title": "Machine Learning in 2 Minutes", "views": 1200000, "engagement_rate": 0.063, "hook_pattern": "speed-explain", "thumbnail_style": "minimal"},
            {"title": "Build a Neural Network from Scratch", "views": 890000, "engagement_rate": 0.079, "hook_pattern": "build-project", "thumbnail_style": "code-screenshot"},
            {"title": "LLMs Explained Simply", "views": 3400000, "engagement_rate": 0.058, "hook_pattern": "simplification", "thumbnail_style": "brain-visual"},
            {"title": "I Fine-Tuned GPT-4 on My Own Data", "views": 670000, "engagement_rate": 0.082, "hook_pattern": "personal-experiment", "thumbnail_style": "face-text"},
        ],
        "data science": [
            {"title": "Data Science Roadmap 2025", "views": 1800000, "engagement_rate": 0.048, "hook_pattern": "roadmap", "thumbnail_style": "path-visual"},
            {"title": "Pandas vs Polars: Which is Faster?", "views": 430000, "engagement_rate": 0.072, "hook_pattern": "comparison", "thumbnail_style": "vs-style"},
            {"title": "SQL for Data Science — Full Course", "views": 2100000, "engagement_rate": 0.041, "hook_pattern": "full-course", "thumbnail_style": "database-icon"},
        ],
    }

    indexed = 0
    niche_lower = niche.lower()

    for key, videos in SAMPLE_COMPETITORS.items():
        if key not in niche_lower:
            continue
        for i, video in enumerate(videos):
            try:
                doc = {
                    "channel_id": f"UC_sample_{key}_{i}",
                    "channel_name": f"Sample {key.title()} Channel",
                    "video_id": f"sample_{key}_{i}",
                    "title": video["title"],
                    "views": video["views"],
                    "likes": int(video["views"] * 0.04),
                    "comments": int(video["views"] * 0.005),
                    "engagement_rate": video["engagement_rate"],
                    "published_at": (datetime.now(timezone.utc) - timedelta(days=30 + i * 7)).isoformat(),
                    "topics": [key],
                    "niche": niche,
                    "audience_level": "beginner",
                    "hook_pattern": video["hook_pattern"],
                    "thumbnail_style": video["thumbnail_style"],
                    "indexed_at": datetime.now(timezone.utc).isoformat(),
                }
                client.index(index="competitor_content", id=f"sample_{key}_{i}", document=doc)
                indexed += 1
            except Exception as e:
                log.warning(f"[trend_ingestion] Failed to seed competitor doc: {e}")

    log.info(f"[trend_ingestion] Seeded {indexed} competitor docs for niche='{niche}'")
    return indexed


def seed_audience_questions(niche: str) -> int:
    """
    Seed Elasticsearch with sample audience questions for demo purposes.
    Returns count of documents indexed.
    """
    from app.mcp.elastic.client import get_elastic_client
    client = get_elastic_client()
    if client is None:
        return 0

    from datetime import datetime, timezone

    SAMPLE_QUESTIONS = {
        "python": [
            ("How long does it take to learn Python?", 1240),
            ("Is Python good for machine learning?", 980),
            ("What Python projects should a beginner build?", 870),
            ("Python vs JavaScript which should I learn first?", 760),
            ("How do I get a job with Python skills?", 690),
            ("What's the best way to practice Python?", 580),
            ("Do I need math for Python programming?", 520),
            ("How do I read someone else's Python code?", 410),
        ],
        "machine learning": [
            ("Do I need to know math for machine learning?", 2100),
            ("What's the difference between AI and machine learning?", 1870),
            ("How much data do I need to train a model?", 960),
            ("Should I use TensorFlow or PyTorch?", 840),
            ("How do I get started with machine learning?", 780),
            ("What is overfitting and how do I prevent it?", 650),
        ],
        "data science": [
            ("How do I become a data scientist?", 3200),
            ("What programming language should a data scientist learn?", 1540),
            ("Is a data science degree worth it?", 1100),
            ("What tools does a data scientist use?", 890),
            ("How do I build a data science portfolio?", 770),
            ("What's the difference between data science and data analytics?", 620),
        ],
    }

    indexed = 0
    niche_lower = niche.lower()

    for key, questions in SAMPLE_QUESTIONS.items():
        if key not in niche_lower:
            continue
        for question, frequency in questions:
            try:
                doc = {
                    "niche": niche,
                    "topic": key,
                    "question": question,
                    "frequency": frequency,
                    "source": "manual_seed",
                    "indexed_at": datetime.now(timezone.utc).isoformat(),
                }
                doc_id = f"{key}_{hash(question) % 100000}"
                client.index(index="audience_questions", id=doc_id, document=doc)
                indexed += 1
            except Exception as e:
                log.warning(f"[trend_ingestion] Failed to seed question: {e}")

    log.info(f"[trend_ingestion] Seeded {indexed} audience questions for niche='{niche}'")
    return indexed
