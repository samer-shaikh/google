from app.services.qwen_service import generate_response
from app.services.model_router import get_model

def thumbnail_agent(topic: str, script: str,plan:str=''):

    prompt = f"""
    You are a YouTube thumbnail expert.

    Topic:
    {topic}

    Script:
    {script}

    Generate:

    1. Thumbnail Text
    2. Thumbnail Concept
    3. Emotion
    4. Color Suggestions
    5. Thumbnail Prompt

    Return in markdown.
    """

    model = get_model(plan,'thumbnail')


    return generate_response(prompt,model)