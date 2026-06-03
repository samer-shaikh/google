from app.services.qwen_service import generate_response
from app.services.model_router import get_model

def research_agent(topic: str, plan:str='normal') -> str:

    prompt = f"""
    You are a YouTube research expert.

    Research this topic:

    {topic}

    Return:

    1. Main ideas
    2. Trending angles
    3. Audience pain points
    4. Viral opportunities
    """
   
    model = get_model(plan, "research")

    return generate_response(prompt,model)