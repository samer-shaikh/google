"""
creator_profile_agent.py

Previously this file had two completely separate implementations:
  1. A CreatorProfileAgent CLASS that did statistical analysis from the DB with no LLM
  2. A standalone creator_profile_agent() FUNCTION that called the LLM

The workflow was calling the function. The /youtube/research route was calling the class.
They produced different schemas and neither knew the other existed.

Fix: The LLM function is now the single authoritative path. The class is kept
for the statistical helper methods (used internally) but run() now delegates
to the LLM function and validates output with Pydantic.
"""
import json
import re
from typing import Optional
from pydantic import BaseModel, ValidationError

from sqlalchemy.orm import Session

from app.models.youtube_video import YouTubeVideo
from app.models.creator_profile import CreatorProfile
from app.services.qwen_service import generate_response
from app.services.model_router import get_model
from app.models.creator_profile import CreatorProfileOutput




# ── Prompt version — bump this string whenever you change the prompt ──────────
PROMPT_VERSION = "v1"


def creator_profile_agent(
    channel_info: dict,
    videos: list[dict],
    plan: str = "normal",
) -> CreatorProfileOutput:
    """
    Analyze a YouTube creator using an LLM and return a validated profile.

    Args:
        channel_info: Dict from youtube_service.get_channel_info()
        videos:       List of dicts from youtube_service.get_recent_videos()
        plan:         User plan tier for model routing

    Returns:
        CreatorProfileOutput (Pydantic model — validated)

    Raises:
        ValueError if the LLM returns malformed JSON or missing required fields
    """
    # Sample to avoid blowing the context window on large channels
    sampled_videos = videos[:30]

    # Build a compact video summary for the prompt
    video_summary = "\n".join(
        f"- \"{v['title']}\" | views: {v.get('views', 0)} | "
        f"likes: {v.get('likes', 0)} | comments: {v.get('comments', 0)}"
        for v in sampled_videos
    )

    prompt = f"""
You are an expert YouTube channel analyst.

Analyze the following YouTube creator and return a JSON profile.

=== CHANNEL INFO ===
Name: {channel_info.get('channel_name', 'Unknown')}
Subscribers: {channel_info.get('subscribers', 0)}
Total Views: {channel_info.get('total_views', 0)}
Video Count: {channel_info.get('video_count', 0)}
Description: {channel_info.get('description', '')[:300]}

=== RECENT VIDEOS ({len(sampled_videos)} sampled) ===
{video_summary}

=== INSTRUCTIONS ===
Return ONLY a valid JSON object. No markdown. No explanation. No preamble.
Use exactly these field names and types:

{{
  "creator_niche": "string — the main niche (e.g. Data Science, Cooking, Finance)",
  "main_topics": ["string", "string", "..."],
  "audience_type": "string — who watches (e.g. beginners learning Python, finance professionals)",
  "audience_level": "string — one of: beginner, intermediate, advanced, mixed",
  "title_style": "string — describe the pattern (e.g. question-based, how-to tutorials, listicles)",
  "description_style": "string — describe how descriptions are written",
  "content_strengths": ["string", "..."],
  "recommended_video_types": ["string", "..."],
  "viral_patterns": ["string", "..."]
}}
"""

    model = get_model(plan, "research")
    raw_response = generate_response(prompt, model)

    # Strip markdown code fences if the LLM wraps its output
    cleaned = re.sub(r"```[a-z]*", "", raw_response).strip().strip("`").strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"CreatorProfileAgent: LLM returned invalid JSON. "
            f"Error: {e}\nRaw response:\n{raw_response[:500]}"
        )

    try:
        profile = CreatorProfileOutput(**data)
    except ValidationError as e:
        raise ValueError(
            f"CreatorProfileAgent: LLM output missing required fields. "
            f"Errors: {e}\nParsed data: {data}"
        )

    return profile


# ── Statistical helpers (used by CreatorProfileAgent.run for DB-based analysis) ─

class CreatorProfileAgent:
    """
    DB-backed agent that reads from youtube_videos, runs local statistical
    analysis, calls the LLM via creator_profile_agent(), and saves the result.

    This is what /youtube/research → profile creation flow should call.
    """

    def fetch_videos(self, user_id: int, db: Session) -> list:
        return (
            db.query(YouTubeVideo)
            .filter(YouTubeVideo.user_id == user_id)
            .all()
        )

    def _orm_videos_to_dicts(self, videos) -> list[dict]:
        return [
            {
                "video_id": v.video_id,
                "title": v.title or "",
                "description": (v.description or "")[:500],
                "views": v.views or 0,
                "likes": v.likes or 0,
                "comments": v.comments or 0,
                "published_at": str(v.published_at) if v.published_at else "",
            }
            for v in videos
        ]

    def save_profile(
        self,
        user_id: int,
        channel_id: str,
        channel_name: str,
        profile_output: CreatorProfileOutput,
        videos_analyzed: int,
        db: Session,
    ) -> CreatorProfile:
        # Upsert: update existing profile if one exists for this user+channel
        existing = (
            db.query(CreatorProfile)
            .filter(
                CreatorProfile.user_id == user_id,
                CreatorProfile.channel_id == channel_id,
            )
            .first()
        )

        profile_data = profile_output.model_dump()

        if existing:
            existing.channel_name = channel_name
            existing.topics = profile_data["main_topics"]
            existing.audience = {
                "audience_type": profile_data["audience_type"],
                "audience_level": profile_data["audience_level"],
            }
            existing.title_style = {"style": profile_data["title_style"]}
            existing.description_style = {"style": profile_data["description_style"]}
            existing.videos_analyzed = videos_analyzed
            existing.prompt_version = PROMPT_VERSION
            profile = existing
        else:
            profile = CreatorProfile(
                user_id=user_id,
                channel_id=channel_id,
                channel_name=channel_name,
                topics=profile_data["main_topics"],
                audience={
                    "audience_type": profile_data["audience_type"],
                    "audience_level": profile_data["audience_level"],
                },
                title_style={"style": profile_data["title_style"]},
                description_style={"style": profile_data["description_style"]},
                videos_analyzed=videos_analyzed,
                prompt_version=PROMPT_VERSION,
            )
            db.add(profile)

        db.commit()
        db.refresh(profile)

        # Mark all processed videos as analyzed
        db.query(YouTubeVideo).filter(
            YouTubeVideo.user_id == user_id,
            YouTubeVideo.is_analyzed == False,  # noqa: E712
        ).update({"is_analyzed": True})
        db.commit()

        return profile

    def run(self, user_id: int, channel_info: dict, db: Session) -> dict:
        """
        Full profile generation flow:
        1. Read videos from DB (saved by YouTubeResearchAgent)
        2. Call LLM via creator_profile_agent()
        3. Validate output
        4. Save to creator_profiles table
        """
        orm_videos = self.fetch_videos(user_id=user_id, db=db)

        if not orm_videos:
            raise Exception(
                "No YouTube videos found in DB. "
                "Run /youtube/research first to fetch and store videos."
            )

        video_dicts = self._orm_videos_to_dicts(orm_videos)

        profile_output = creator_profile_agent(
            channel_info=channel_info,
            videos=video_dicts,
        )

        profile = self.save_profile(
            user_id=user_id,
            channel_id=channel_info["channel_id"],
            channel_name=channel_info["channel_name"],
            profile_output=profile_output,
            videos_analyzed=len(orm_videos),
            db=db,
        )

        return {
            "success": True,
            "profile_id": profile.id,
            "videos_analyzed": len(orm_videos),
            "profile": profile_output.model_dump(),
        }
