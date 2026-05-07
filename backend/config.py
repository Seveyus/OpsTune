import os

class Config:
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    MOCK_DB_PATH = "backend/evaluation/mock_db.json"

config = Config()
