"""Configuration module for Kicktipp Bot."""

import os
from datetime import timedelta
from typing import Optional


class Config:
    """Configuration class containing all environment variables and constants."""

    # Base URLs
    BASE_URL = "https://www.kicktipp.de/"
    LOGIN_URL = "https://www.kicktipp.de/info/profil/login/"

    # Cache for lazy-loaded env vars
    _cache = {}

    @classmethod
    def _get_env(cls, key: str, default: str = None) -> Optional[str]:
        """Lazy-load environment variable with caching."""
        if key not in cls._cache:
            cls._cache[key] = os.getenv(key, default)
        return cls._cache[key]

    @property
    def EMAIL(self) -> Optional[str]:
        return self._get_env("KICKTIPP_EMAIL")

    @property
    def PASSWORD(self) -> Optional[str]:
        return self._get_env("KICKTIPP_PASSWORD")

    @property
    def NAME_OF_COMPETITION(self) -> Optional[str]:
        return self._get_env("KICKTIPP_NAME_OF_COMPETITION")

    @property
    def COMPETITIONS_RAW(self) -> Optional[str]:
        return self._get_env("KICKTIPP_COMPETITIONS")

    @classmethod
    def COMPETITIONS(cls) -> list:
        """Get list of competitions from KICKTIPP_COMPETITIONS or fall back to single NAME_OF_COMPETITION."""
        competitions_raw = cls._get_env("KICKTIPP_COMPETITIONS")
        if competitions_raw:
            return [c.strip() for c in competitions_raw.split(",") if c.strip()]
        name = cls._get_env("KICKTIPP_NAME_OF_COMPETITION")
        if name:
            return [name]
        return []

    @classmethod
    def RUN_EVERY_X_MINUTES(cls) -> int:
        return int(cls._get_env("KICKTIPP_RUN_EVERY_X_MINUTES", "60"))

    @classmethod
    def OVERWRITE_TIPS(cls) -> bool:
        return cls._get_env("OVERWRITE_TIPS", "false").lower() == "true"

    @classmethod
    def PREDICTOR(cls) -> str:
        return cls._get_env("PREDICTOR", "ai")

    @classmethod
    def OPENAI_API_KEY(cls) -> Optional[str]:
        return cls._get_env("OPENAI_API_KEY")

    @classmethod
    def OPENAI_MODEL(cls) -> str:
        return cls._get_env("OPENAI_MODEL", "gpt-5.5")

    @classmethod
    def CHROMEDRIVER_PATH(cls) -> Optional[str]:
        return cls._get_env("CHROMEDRIVER_PATH")

    @classmethod
    def HOURS_UNTIL_GAME(cls) -> int:
        return int(cls._get_env("KICKTIPP_HOURS_UNTIL_GAME", "2"))

    @classmethod
    def TIME_UNTIL_GAME(cls) -> timedelta:
        return timedelta(hours=cls.HOURS_UNTIL_GAME())

    @classmethod
    def ZAPIER_URL(cls) -> Optional[str]:
        return cls._get_env("ZAPIER_URL")

    @classmethod
    def NTFY_URL(cls) -> Optional[str]:
        return cls._get_env("NTFY_URL")

    @classmethod
    def NTFY_USERNAME(cls) -> Optional[str]:
        return cls._get_env("NTFY_USERNAME")

    @classmethod
    def NTFY_PASSWORD(cls) -> Optional[str]:
        return cls._get_env("NTFY_PASSWORD")

    @classmethod
    def WEBHOOK_URL(cls) -> Optional[str]:
        return cls._get_env("WEBHOOK_URL")

    @classmethod
    def GROUP_NOTIFICATIONS(cls) -> bool:
        return cls._get_env("GROUP_NOTIFICATIONS", "false").lower() == "true"

    @classmethod
    def validate_required_config(cls) -> bool:
        """Validate that all required configuration is present."""
        # Base required vars
        required_vars = [cls._get_env("KICKTIPP_EMAIL"), cls._get_env("KICKTIPP_PASSWORD")]

        # If using ai predictor, require OPENAI_API_KEY
        if cls.PREDICTOR() == 'ai':
            required_vars.append(cls.OPENAI_API_KEY())

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
