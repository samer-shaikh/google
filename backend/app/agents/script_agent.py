from app.services.qwen_service import generate_response
from app.services.model_router import get_model

def script_agent(topic: str, research: str, selected_idea: str, plan: str='normal'):

    prompt = f"""
            You are an expert YouTube script writer.

            Original Topic:
            {topic}

            Selected Video Idea:
            {selected_idea}

            Research:
            {research}

            Create a complete YouTube script.

            Requirements:

            - Strong hook in first 15 seconds
            - Clear introduction
            - Main content with multiple sections
            - Examples where appropriate
            - Engaging storytelling style
            - Conversational tone
            - Strong CTA at the end

            Format:

            # Hook

            # Introduction

            # Main Content

            # Conclusion

            # Call To Action

            Make the script detailed, engaging, and optimized for viewer retention.
            """

    model = get_model(plan,'script')

    return generate_response(prompt,model)