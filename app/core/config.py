from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "sqlite:///./lsp.db"
    preapproval_threshold: int = 650
    isoftpull_api_key: str = ""
    isoftpull_account_id: str = ""
    sendgrid_api_key: str = ""
    sender_email: str = ""

    class Config:
        env_file = ".env"

settings = Settings()
