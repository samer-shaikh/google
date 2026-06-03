from app.database import Base, engine

from app.models.creator_profile import CreatorProfile

Base.metadata.create_all(bind=engine)

print("Tables created")