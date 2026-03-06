import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")

client = MongoClient(MONGO_URI)

db = client["heuruxagent_db"]

evaluations_collection = db["evaluations"]
feedback_collection = db["feedback"]
screenshots_collection = db["screenshots"]