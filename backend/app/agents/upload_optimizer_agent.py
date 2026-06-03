from app.services.qwen_service import generate_response
from app.services.model_router import get_model

def upload_optimizer_agent(topic: str, script: str, plan: str='normal'):

    prompt = f"""
    You are a YouTube SEO expert.

    Topic:
    {topic}

    Script:
    {script}

    Generate:

    1. SEO Title
    2. YouTube Description
    3. 15 Tags
    4. 10 Hashtags

    Return in markdown.
    1 title
    1 description (100 words max)
    10 tags
    5 hashtags
    """


    model = get_model(plan,'upload_optimizer')

    return generate_response(prompt,model)