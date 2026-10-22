from pydantic import Field, field_validator
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
    MAX_UPLOAD_MB: int = 100
    DOCUMENT_CONCURRENCY: int = 2
    LLM_CONCURRENCY: int = 4
    EMBEDDING_CONCURRENCY: int = 2
    EMBEDDING_BATCH_SIZE: int = Field(default=16, le=100)
    ANALYSIS_CONTEXT_CHARS: int = Field(default=24000, ge=4000)

    # Keep resource limits positive, including when supplied through .env.
    @field_validator("MAX_UPLOAD_MB", "DOCUMENT_CONCURRENCY", "LLM_CONCURRENCY",
                     "EMBEDDING_CONCURRENCY", "EMBEDDING_BATCH_SIZE", "ANALYSIS_CONTEXT_CHARS")
    @classmethod
    def positive_limit(cls, value: int) -> int:
        if value < 1:
            raise ValueError("Resource limits must be positive")
        return value

@lru_cache()
def get_settings():
    return Settings()
