"""Notification event models for structured data storage."""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Tuple


@dataclass
class NotificationEvent:
    """Represents a notification event for a tipped game.
    
    This dataclass provides structured storage for notification data with both
    generic webhook fields and Zapier-compatible field names.
    """
    
    home_team: str
    away_team: str
    quotes: List[str]
    tip: Tuple[int, int]
    game_time: datetime
    competition: str = ""
    
    def to_dict(self) -> dict:
        """Convert the event to a dictionary suitable for webhook payloads.
        
        Returns both generic webhook fields and Zapier-compatible fields for
        backward compatibility with existing integrations.
        """
        return {
            # Generic webhook fields
            "home_team": self.home_team,
            "away_team": self.away_team,
            "quotes": self.quotes,
            "tip": list(self.tip),
            "time": self.game_time.strftime('%d.%m.%y %H:%M'),
            "timestamp": self.game_time.isoformat(),
            "competition": self.competition,
            
            # Zapier-compatible fields
            "date": self.game_time.isoformat(),
            "team1": self.home_team,
            "team2": self.away_team,
            "quoteteam1": self.quotes[0] if len(self.quotes) > 0 else '',
            "quotedraw": self.quotes[1] if len(self.quotes) > 1 else '',
            "quoteteam2": self.quotes[2] if len(self.quotes) > 2 else '',
            "tipteam1": self.tip[0],
            "tipteam2": self.tip[1]
        }
    
    def __str__(self) -> str:
        """String representation of the notification event."""
        comp = f" [{self.competition}]" if self.competition else ""
        return f"{self.home_team} - {self.away_team}: {self.tip[0]}:{self.tip[1]}{comp} ({self.game_time.strftime('%d.%m.%y %H:%M')})"
