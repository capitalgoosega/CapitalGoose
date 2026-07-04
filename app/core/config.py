from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "sqlite:///./lsp.db"
    gmail_user: str = ""
    gmail_app_password: str = ""
    sender_email: str = ""

    class Config:
        env_file = ".env"

settings = Settings()
