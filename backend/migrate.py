"""
migrate.py — Drop and recreate creator_profiles and youtube_videos
with the corrected schema.

Safe to run because these tables have no real production data yet.

Run from the backend folder:
    python migrate.py
"""
import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URl") or os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URl not set in .env")
    sys.exit(1)

engine = create_engine(DATABASE_URL)

print("Connecting to database...")

with engine.connect() as conn:
    print("Dropping creator_profiles...")
    conn.execute(text("DROP TABLE IF EXISTS creator_profiles CASCADE"))

    print("Dropping youtube_videos...")
    conn.execute(text("DROP TABLE IF EXISTS youtube_videos CASCADE"))

    print("Dropping youtube_accounts...")
    conn.execute(text("DROP TABLE IF EXISTS youtube_accounts CASCADE"))

    print("Dropping generations...")
    conn.execute(text("DROP TABLE IF EXISTS generations CASCADE"))

    conn.commit()
    print("Tables dropped.")

# Now recreate using the updated SQLAlchemy models
print("Recreating tables from models...")

from app.database import Base

# Import every model so SQLAlchemy registers them all before create_all
from app.models.user import User                          # noqa
from app.models.youtube_account import YouTubeAccount     # noqa
from app.models.youtube_video import YouTubeVideo         # noqa
from app.models.creator_profile import CreatorProfile     # noqa
from app.models.generation import Generation              # noqa
from app.models.plan import Plan                          # noqa
from app.models.thread import Thread                      # noqa
from app.models.project import Project                    # noqa

Base.metadata.create_all(bind=engine)

print("Done. Verifying new columns...\n")

from sqlalchemy import inspect
inspector = inspect(engine)

print("creator_profiles columns:")
for col in inspector.get_columns("creator_profiles"):
    print(f"  {col['name']:25s}  {str(col['type'])}")

print("\nyoutube_videos columns:")
for col in inspector.get_columns("youtube_videos"):
    print(f"  {col['name']:25s}  {str(col['type'])}")

print("\nyoutube_accounts columns:")
for col in inspector.get_columns("youtube_accounts"):
    print(f"  {col['name']:25s}  {str(col['type'])}")

print("\nMigration complete. Run python check.py again to verify.")
