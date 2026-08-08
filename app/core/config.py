from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "sqlite:///./lsp.db"
    gmail_user: str = ""
    gmail_app_password: str = ""
    sender_email: str = ""
    resend_api_key: str = ""
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_refresh_token: str = ""

    class Config:
        env_file = ".env"

settings = Settings()
