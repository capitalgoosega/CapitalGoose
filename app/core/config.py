from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "sqlite:///./lsp.db"
    gmail_user: str = ""
    gmail_app_password: str = ""
    sender_email: str = ""
    reply_to_email: str = ""
    # SMTP (e.g. Titan: smtp.titan.email, port 465). When set, it is used instead of the Gmail API.
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    resend_api_key: str = ""
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_refresh_token: str = ""

    class Config:
        env_file = ".env"

settings = Settings()
