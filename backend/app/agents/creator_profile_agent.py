"""
creator_profile_agent.py

Analyses YouTube channel data with the LLM and returns a validated profile.
After saving to PostgreSQL, syncs to MongoDB creator_memory so that
content_strengths and viral_patterns are persisted for downstream agents.
"""
import json
import re
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.models.youtube_video import YouTubeVideo
from app.models.creator_profile import CreatorProfile, CreatorProfileOutput
from app.services.llm_provider import generate_response
from app.services.model_router import get_model

PROMPT_VERSION = "v1"


def creator_profile_agent(
    channel_info: dict,
    videos: list[dict],
    plan: str = "normal",
) -> CreatorProfileOutput:
    """
    Analyze a YouTube creator using the LLM and return a validated profile.
    Raises ValueError on malformed LLM output — never stores garbage.
    """
    sampled_videos = videos[:30]

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


class CreatorProfileAgent:
    """DB-backed orchestrator: fetch videos → LLM analysis → save."""

    def fetch_videos(self, user_id: int, db: Session) -> list:
        return (
            db.query(YouTubeVideo)
            .filter(YouTubeVideo.user_id == user_id)
            .all()
        )

    def _orm_to_dicts(self, videos) -> list[dict]:
        return [
            {
                "video_id":     v.video_id,
                "title":        v.title or "",
                "description":  (v.description or "")[:500],
                "views":        v.views or 0,
                "likes":        v.likes or 0,
                "comments":     v.comments or 0,
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
        existing = (
            db.query(CreatorProfile)
            .filter(
                CreatorProfile.user_id == user_id,
                CreatorProfile.channel_id == channel_id,
            )
            .first()
        )

        data = profile_output.model_dump()

        if existing:
            existing.channel_name      = channel_name
            existing.topics            = data["main_topics"]
            existing.audience          = {
                "audience_type":  data["audience_type"],
                "audience_level": data["audience_level"],
            }
            existing.title_style       = {"style": data["title_style"]}
            existing.description_style = {"style": data["description_style"]}
            existing.videos_analyzed   = videos_analyzed
            existing.prompt_version    = PROMPT_VERSION
            profile = existing
        else:
            profile = CreatorProfile(
                user_id=           user_id,
                channel_id=        channel_id,
                channel_name=      channel_name,
                topics=            data["main_topics"],
                audience={
                    "audience_type":  data["audience_type"],
                    "audience_level": data["audience_level"],
                },
                title_style=       {"style": data["title_style"]},
                description_style= {"style": data["description_style"]},
                videos_analyzed=   videos_analyzed,
                prompt_version=    PROMPT_VERSION,
            )
            db.add(profile)

        db.commit()
        db.refresh(profile)

        db.query(YouTubeVideo).filter(
            YouTubeVideo.user_id == user_id,
            YouTubeVideo.is_analyzed == False,  # noqa: E712
        ).update({"is_analyzed": True})
        db.commit()

        return profile

    def _sync_to_mongodb(
        self,
        user_id: int,
        channel_id: str,
        channel_name: str,
        profile_output: CreatorProfileOutput,
    ) -> None:
        try:
            from app.memory import get_creator_memory_service
            svc = get_creator_memory_service()
            profile_dict = profile_output.model_dump()

            profile_data_for_memory = {
                "creator_niche":           profile_dict["creator_niche"],
                "main_topics":             profile_dict["main_topics"],
                "topics":                  profile_dict["main_topics"],
                "audience_type":           profile_dict["audience_type"],
                "audience_level":          profile_dict["audience_level"],
                "title_style":             profile_dict["title_style"],
                "description_style":       profile_dict["description_style"],
                "content_strengths":       profile_dict["content_strengths"],
                "viral_patterns":          profile_dict["viral_patterns"],
                "recommended_video_types": profile_dict["recommended_video_types"],
            }

            svc.sync_from_profile(
                user_id=user_id,
                profile_data=profile_data_for_memory,
                channel_id=channel_id,
                channel_name=channel_name,
            )
            print(
                f"[CreatorProfileAgent] synced to MongoDB — "
                f"viral_patterns={len(profile_dict['viral_patterns'])} | "
                f"content_strengths={len(profile_dict['content_strengths'])}"
            )
        except Exception as e:
            print(f"[CreatorProfileAgent] MongoDB sync warning (non-fatal): {e}")

    def run(self, user_id: int, channel_info: dict, db: Session) -> dict:
        orm_videos = self.fetch_videos(user_id=user_id, db=db)

        if not orm_videos:
            raise Exception(
                "No YouTube videos in DB. "
                "Run /youtube/research first."
            )

        video_dicts    = self._orm_to_dicts(orm_videos)
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

        self._sync_to_mongodb(
            user_id=user_id,
            channel_id=channel_info["channel_id"],
            channel_name=channel_info["channel_name"],
            profile_output=profile_output,
        )

        return {
            "success":         True,
            "profile_id":      profile.id,
            "videos_analyzed": len(orm_videos),
            "profile":         profile_output.model_dump(),
        }
