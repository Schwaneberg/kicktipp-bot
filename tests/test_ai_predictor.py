import pytest
from datetime import datetime

from kicktipp_bot.models.game import Game
from kicktipp_bot.core.predictor import AIPredictor


class DummyOpenAI:
    pass


def test_ai_predictor_valid(monkeypatch):
    # Monkeypatch _call_api to return a valid response
    monkeypatch.setattr(AIPredictor, '_call_api', lambda self, h, a, k, c: {'home_score': 1, 'away_score': 2})
    # Ensure we can instantiate without real openai (AIPredictor imports openai in __init__)
    # Provide a dummy module so import succeeds
    import sys
    sys.modules.setdefault('openai', DummyOpenAI())

    p = AIPredictor()
    g = Game('Home', 'Away', ['1.0', '2.0', '3.0'], datetime.now())
    assert p.predict(g, 'comp') == (1, 2)


def test_ai_predictor_invalid_response(monkeypatch):
    monkeypatch.setattr(AIPredictor, '_call_api', lambda self, h, a, k, c: {'home_score': 'x', 'away_score': 2})
    import sys
    sys.modules.setdefault('openai', DummyOpenAI())

    p = AIPredictor()
    g = Game('Home', 'Away', ['1.0', '2.0', '3.0'], datetime.now())
    with pytest.raises(Exception):
        p.predict(g, 'comp')
