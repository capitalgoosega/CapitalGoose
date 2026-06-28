from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "sqlite:///./lsp.db"
    sendgrid_api_key: str = ""
    sender_email: str = ""

    class Config:
        env_file = ".env"

settings = Settings()
