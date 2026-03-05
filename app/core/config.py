import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    DATABASE_URL = os.getenv("DATABASE_URL")
    SHOPIFY_STORE = os.getenv("SHOPIFY_STORE")
    SHOPIFY_TOKEN = os.getenv("SHOPIFY_TOKEN")
    API_VERSION = os.getenv("API_VERSION", "2026-01")

settings = Settings()