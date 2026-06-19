"""Predictor implementations and factory.

Provides a pluggable predictor interface with two implementations:
- QuotesPredictor: wraps existing Game.calculate_tip()
- AIPredictor: calls OpenAI to get structured JSON predictions

Both implementations expose `predict(game, competition)` -> (int, int).
"""

import json
import logging
import time
from typing import Tuple

from ..config import Config
from ..models.game import Game

logger = logging.getLogger(__name__)


class BasePredictor:
    def predict(self, game: Game, competition: str) -> Tuple[int, int]:
        raise NotImplementedError()


class QuotesPredictor(BasePredictor):
    def predict(self, game: Game, competition: str) -> Tuple[int, int]:
        # Use the existing quote-based algorithm
        return game.calculate_tip()


class AIPredictor(BasePredictor):
    def __init__(self):
        try:
            import openai
            self.openai = openai
            # Set API key on the module (openai accepts this)
            if Config.OPENAI_API_KEY:
                try:
                    # Newer openai libs prefer openai.api_key
                    self.openai.api_key = Config.OPENAI_API_KEY
                except Exception:
                    pass
        except Exception as e:
            logger.error("openai package not available: %s", e)
            raise

        self.model = Config.OPENAI_MODEL

    def _call_api(self, home: str, away: str, kickoff_iso: str, competition: str):
        # Try to use Responses API if available, else fallback to ChatCompletion with JSON parse
        system = "You are an expert football (soccer) score predictor for German Bundesliga-style prediction pools."
        user = f"Predict the final score for: {home} vs {away}, kickoff {kickoff_iso}, competition context: {competition}. Respond with JSON: {json.dumps({'home_score': 'int', 'away_score': 'int'})}"

        # Prefer Responses API if present
        try:
            if hasattr(self.openai, 'responses'):
                # Newer client: openai.responses.create
                schema = {
                    "type": "object",
                    "properties": {
                        "home_score": {"type": "integer", "minimum": 0},
                        "away_score": {"type": "integer", "minimum": 0}
                    },
                    "required": ["home_score", "away_score"],
                    "additionalProperties": False
                }
                resp = self.openai.responses.create(
                    model=self.model,
                    input=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                    text_format={"type": "json_schema", "json_schema": {"name": "score_prediction", "schema": schema}},
                    max_output_tokens=50,
                )
                # Extract the JSON-like output
                # Different SDK versions return different shapes; try common ones
                if hasattr(resp, 'output'):
                    # find the parsed JSON
                    for item in getattr(resp, 'output'):
                        if isinstance(item, dict) and 'content' in item:
                            try:
                                return item['content']
                            except Exception:
                                continue
                # fallback raw
                raw = getattr(resp, 'text', None) or getattr(resp, 'output_text', None)
                if raw:
                    return json.loads(raw)

        except Exception:
            logger.debug("Responses API path not available or failed, falling back to ChatCompletion", exc_info=True)

        # Fallback: ChatCompletion -> strict JSON only
        try:
            prompt = [
                {"role": "system", "content": system},
                {"role": "user", "content": user + "\nReturn a single JSON object only, e.g. {\"home_score\":1,\"away_score\":2}."}
            ]
            chat = self.openai.ChatCompletion.create(
                model=self.model,
                messages=prompt,
                max_tokens=30,
                temperature=0.0
            )
            content = None
            if isinstance(chat, dict):
                # legacy response
                content = chat.get('choices', [{}])[0].get('message', {}).get('content')
            else:
                try:
                    content = chat.choices[0].message.content
                except Exception:
                    content = None

            if not content:
                raise ValueError("Empty response from ChatCompletion")

            # Parse JSON from content
            return json.loads(content.strip())

        except Exception as e:
            logger.error("OpenAI API call failed: %s", e)
            raise

    def predict(self, game: Game, competition: str) -> Tuple[int, int]:
        home = game.home_team
        away = game.away_team
        kickoff_iso = game.game_time.isoformat()

        retries = 2
        delay = 1
        last_exc = None
        for attempt in range(retries):
            try:
                resp = self._call_api(home, away, kickoff_iso, competition)

                # If the responses.create path returned dict-like with fields
                if isinstance(resp, dict) and 'home_score' in resp and 'away_score' in resp:
                    hs = resp['home_score']
                    aw = resp['away_score']
                else:
                    # If we got a nested structure, try to find keys
                    if isinstance(resp, dict):
                        hs = resp.get('home_score')
                        aw = resp.get('away_score')
                    else:
                        raise ValueError('Unexpected response shape from OpenAI')

                # Defensive validation
                if not isinstance(hs, int) or not isinstance(aw, int):
                    raise ValueError('OpenAI returned non-integer scores')
                if hs < 0 or aw < 0:
                    raise ValueError('OpenAI returned negative score')

                return hs, aw

            except Exception as e:
                last_exc = e
                logger.warning("OpenAI predictor attempt %d failed: %s", attempt + 1, e)
                time.sleep(delay)
                delay *= 2

        # All attempts failed
        logger.error("AI predictor failed for %s vs %s: %s", home, away, last_exc)
        raise last_exc


def get_predictor():
    if Config.PREDICTOR == 'quotes':
        return QuotesPredictor()
    return AIPredictor()
