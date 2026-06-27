from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore"
    )

    DATABASE_URL: str
    REDIS_URL: str
    MINIO_ENDPOINT: str
    MINIO_ACCESS_KEY: str
    MINIO_SECRET_KEY: str
    ENVIRONMENT: str = "development"
    GEMINI_API_KEY: str = ""  
    GITHUB_TOKEN: str = ""

# Global configurations instance
settings = Settings()
