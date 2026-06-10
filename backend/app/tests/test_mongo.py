from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()

uri = os.getenv("MONGODB_URI")



client = MongoClient(uri)

db = client["ai_content_studio"]

result = db.creator_memory.insert_one({
    "test": "hackathon",
    "status": "working"
})

print(result.inserted_id)