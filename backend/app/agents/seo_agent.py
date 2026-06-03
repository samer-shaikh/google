from app.services.qwen_service import generate_response
from app.services.model_router import get_model

def seo_agent(topic: str, script: str,plan:str):

    prompt = f"""
    You are a YouTube SEO expert.

    Topic:
    {topic}

    Script:
    {script}

    Generate:

    1. SEO Title
    2. Description
    3. 15 Tags
    4. 10 Hashtags

    Return in clean markdown.
    """


    model = get_model(plan, "seo")


    return generate_response(prompt,model)