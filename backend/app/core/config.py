import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Project AEGIS"
    API_V1_STR: str = "/api/v1"
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "aegis_super_secret_key_change_me_in_production_12345")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 1 week
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./aegis.db")
    
    # Gemini AI API Key
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    
    class Config:
        case_sensitive = True

settings = Settings()
