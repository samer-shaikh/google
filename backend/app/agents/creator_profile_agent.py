from app.services.qwen_service import generate_response
from app.services.model_router import get_model
import json

def creator_profile_agent(channel_info, videos,plan:str = "normal"):

    prompt = f"""
    Analyze this YouTube creator.

    Channel:
    {channel_info}

    Videos:
    {videos}

    Return:

    - Main Topics
    - Audience
    - Title Style
    - Description Style

    Output JSON only.
    """

    model = get_model(plan, "research")

    response = generate_response(prompt, model)

    return json.loads(response)