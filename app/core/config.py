import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Application settings loaded from environment variables and .env."""

    app_name: str = os.getenv("APP_NAME", "Asset Risk Platform")
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/asset_risk"
    )
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "change-me-in-production")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))


settings = Settings()
