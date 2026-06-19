"""Configuration module for Kicktipp Bot."""

import os
from datetime import timedelta
from typing import Optional


class Config:
    """Configuration class containing all environment variables and constants."""

    # Base URLs
    BASE_URL = "https://www.kicktipp.de/"
    LOGIN_URL = "https://www.kicktipp.de/info/profil/login/"

    # Required environment variables
    EMAIL: Optional[str] = os.getenv("KICKTIPP_EMAIL")
    PASSWORD: Optional[str] = os.getenv("KICKTIPP_PASSWORD")
    NAME_OF_COMPETITION: Optional[str] = os.getenv(
        "KICKTIPP_NAME_OF_COMPETITION")

    # Support multiple competitions via comma separated list. Fall back to single name.
    COMPETITIONS_RAW: Optional[str] = os.getenv("KICKTIPP_COMPETITIONS")
    @classmethod
    def COMPETITIONS(cls):
        if cls.COMPETITIONS_RAW:
            return [c.strip() for c in cls.COMPETITIONS_RAW.split(",") if c.strip()]
        if cls.NAME_OF_COMPETITION:
            return [cls.NAME_OF_COMPETITION]
        return []

    # Optional environment variables with defaults
    RUN_EVERY_X_MINUTES: Optional[int] = int(
        os.getenv("KICKTIPP_RUN_EVERY_X_MINUTES", "60"))
    OVERWRITE_TIPS: Optional[bool] = os.getenv("OVERWRITE_TIPS", "false").lower() == "true"

    # Predictor selection: 'ai' or 'quotes'
    PREDICTOR: str = os.getenv("PREDICTOR", "ai")

    # OpenAI configuration (only required when PREDICTOR=ai)
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-5.5")

    # Chrome driver path
    CHROMEDRIVER_PATH: Optional[str] = os.getenv("CHROMEDRIVER_PATH")

    # Time configuration
    HOURS_UNTIL_GAME: Optional[int] = int(
        os.getenv("KICKTIPP_HOURS_UNTIL_GAME", "2"))
    TIME_UNTIL_GAME: timedelta = timedelta(hours=HOURS_UNTIL_GAME)

    # Notification URLs
    ZAPIER_URL: Optional[str] = os.getenv("ZAPIER_URL")
    NTFY_URL: Optional[str] = os.getenv("NTFY_URL")
    NTFY_USERNAME: Optional[str] = os.getenv("NTFY_USERNAME")
    NTFY_PASSWORD: Optional[str] = os.getenv("NTFY_PASSWORD")
    WEBHOOK_URL: Optional[str] = os.getenv("WEBHOOK_URL")
    GROUP_NOTIFICATIONS: bool = os.getenv("GROUP_NOTIFICATIONS", "false").lower() == "true"

    @classmethod
    def validate_required_config(cls) -> bool:
        """Validate that all required configuration is present."""
        # Base required vars
        required_vars = [cls.EMAIL, cls.PASSWORD]

        # If using ai predictor, require OPENAI_API_KEY
        if cls.PREDICTOR == 'ai':
            required_vars.append(cls.OPENAI_API_KEY)

        # Require at least one competition name
        if not cls.COMPETITIONS():
            return False

        return all(var is not None for var in required_vars)

    @classmethod
    def get_tipp_url(cls) -> str:
        """Get the URL for the tipping page for the default competition."""
        return f"https://www.kicktipp.de/{cls.NAME_OF_COMPETITION}/tippabgabe"

    @classmethod
    def get_tipp_url_for_competition(cls, competition: str) -> str:
        """Get the URL for the tipping page for a given competition slug."""
        return f"https://www.kicktipp.de/{competition}/tippabgabe"
