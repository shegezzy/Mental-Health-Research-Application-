import os
from backend.config.env_loader import load_env

load_env()


class Settings:
    # Google Sheets
    GOOGLE_SHEETS_SPREADSHEET_ID: str = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID", "")
    GOOGLE_SERVICE_ACCOUNT_JSON: str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")  # JSON string

    # OpenAI
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-5.4-nano")



    # App
    APP_ENV: str = os.getenv("APP_ENV", "development")
    CORS_ORIGINS: list = os.getenv("CORS_ORIGINS", "*").split(",")

    # Risk thresholds (based on scored questions Q6–Q9, Q12–Q16, Q18–Q20 = 13 questions * 5 max = 65 max)
    LOW_RISK_MAX: int = int(os.getenv("LOW_RISK_MAX", "26"))       # ≤ 40%
    MODERATE_RISK_MAX: int = int(os.getenv("MODERATE_RISK_MAX", "39"))  # ≤ 60%
    HIGH_RISK_MAX: int = int(os.getenv("HIGH_RISK_MAX", "52"))     # ≤ 80%
    # > 52 = Very High Risk

settings = Settings()
