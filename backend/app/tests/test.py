from app.agents.youtube_research_agent import YouTubeResearchAgent
from app.database import SessionLocal

def test():
    db = SessionLocal()

    try:
        agent = YouTubeResearchAgent()

        result = agent.run(
            user_id=1,
            db=db
        )

        print(result)

    finally:
        db.close()

test()