import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    PROJECT_NAME: str = "Synora"
    API_V1_STR: str = "/api/v1"
    
    DATABASE_URL: str
    GEMINI_API_KEY: str
    PINECONE_API_KEY: str
    PINECONE_ENV: str
    PINECONE_INDEX_NAME: str = "synora"
    UPLOADTHING_TOKEN: str
    REDIS_URL: str
    GOOGLE_CLIENT_ID: str

@lru_cache()
def get_settings():
    return Settings()
