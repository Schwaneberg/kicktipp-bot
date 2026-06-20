"""Game tipping module for handling the core betting logic.

This module was extended to support multiple competitions per run and a
pluggable predictor interface. Predictions are cached in-memory for the
duration of a single tip cycle so that AI calls happen at most once per
unique match per run.
"""

import logging
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
from time import sleep
from typing import Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.common.exceptions import NoSuchElementException, WebDriverException

from ..config import Config
from ..models.game import Game
from .notifications import NotificationManager
from .predictor import QuotesPredictor, get_predictor
from ..utils.selenium_utils import SeleniumUtils
from .table_processors import TimeExtractor, TableRowProcessor, GameDataExtractor

logger = logging.getLogger(__name__)


class GameTippingError(Exception):
    """Custom exception for game tipping failures."""
    pass


class GameTipper:
    """Handles the core game tipping functionality."""

    def __init__(self, driver: WebDriver, notification_manager: NotificationManager):
        self.driver = driver
        self.notification_manager = notification_manager
        self.table_processor = TableRowProcessor(driver)
        # State management
        self.last_seen_time = None
        self.processed_count = 0
        self.game_number = 0

        # Per-run state
        self.predictions_cache = {}
        self.existing_tips = {}
        self.current_competition = ''

    def _is_valid_tip(self, tip) -> bool:
        return (
            isinstance(tip, (tuple, list))
            and len(tip) == 2
            and all(isinstance(x, int) and x >= 0 for x in tip)
        )

    def tip_all_games(self) -> None:
        """Process and tip all available games for configured competitions.

        Iterates over `Config.COMPETITIONS()` and maintains a per-run in-memory
        cache of predictions so the AI is queried at most once per unique
        match per run. If a bet already exists in any configured competition,
        that tip will be reused for the same match in all other competitions.
        """
        logger.info("Starting game tipping process")

        competitions = Config.COMPETITIONS()
        if not competitions:
            logger.warning("No competitions configured to tip")
            return

        # First pass: scan competitions and collect already placed tips
        try:
            for competition in competitions:
                logger.info(f"Scanning competition for existing bets: {competition}")
                self.current_competition = competition
                self._prepare_competition_page(competition)
                self._reset_state()
                self._collect_existing_tips_for_competition()

            # Second pass: navigate again and tip all unfilled games
            for competition in competitions:
                logger.info(f"Processing competition: {competition}")
                self.current_competition = competition
                self._prepare_competition_page(competition)

                # Get the number of games available
                games_count = self._get_games_count()
                if games_count == 0:
                    logger.warning("No games found to process for %s", competition)
                    continue

                logger.info(f"Found {games_count} games to process for {competition}")

                # Reset state for this competition
                self._reset_state()

                # Process table rows; predictor and cache are on self
                self._process_all_table_rows()

                # Submit all tips for this competition
                self._submit_all_tips()

                # Debug mode sleep
                if self._is_debug_mode() and Config.RUN_EVERY_X_MINUTES() != 0:
                    logger.info(
                        "Local debug mode - sleeping for 5 seconds to review results")
                    sleep(5)

        except GameTippingError:
            raise
        except WebDriverException as e:
            raise GameTippingError(f"WebDriver error during tipping: {e}")
        except Exception as e:
            raise GameTippingError(f"Unexpected error during tipping: {e}")
        finally:
            # Always send grouped notifications at the end, even if errors occurred
            self.notification_manager.send_grouped_notifications()

    def _prepare_competition_page(self, competition: str) -> None:
        """Open the tipping page for a competition and accept any dialogs."""
        logger.debug("Navigating to tipping page for %s", competition)
        self.driver.get(Config.get_tipp_url_for_competition(competition))

        if not SeleniumUtils.wait_for_page_load(self.driver):
            raise GameTippingError("Tipping page failed to load")

        sleep(1)
        self._accept_terms_and_conditions()

    def _collect_existing_tips_for_competition(self) -> None:
        """Collect already placed tips from the currently loaded competition page."""
        all_rows = self.table_processor.get_all_table_rows()
        if not all_rows:
            logger.warning("No table rows found while collecting existing tips")
            return

        for row_index, _ in enumerate(all_rows):
            try:
                row, row_class = self.table_processor.get_row_safely(
                    all_rows, row_index)
                if row is None or row_class is None:
                    continue

                if 'rowheader' in row_class:
                    self._process_rowheader(row, row_index)
                elif 'datarow' in row_class:
                    self._collect_datarow(row)
            except Exception as e:
                logger.error(f"Error collecting tips from row {row_index}: {e}")
                continue

    def _collect_datarow(self, data_row) -> None:
        """Collect an already placed tip from a game row, if present."""
        home_team = GameDataExtractor.extract_team_name(
            data_row, 2, 'home')
        away_team = GameDataExtractor.extract_team_name(
            data_row, 3, 'away')

        if not home_team or not away_team:
            return

        game_time = TimeExtractor.extract_from_datarow(
            data_row, self.last_seen_time)

        tip_fields = GameDataExtractor.get_tip_fields(data_row)
        if not tip_fields:
            return

        home_tip_field, away_tip_field = tip_fields
        existing_tip = self._get_tip_value(home_tip_field, away_tip_field)
        if not existing_tip:
            return

        match_id = f"{home_team}|{away_team}|{game_time.isoformat()}"
        if match_id not in self.existing_tips:
            self.existing_tips[match_id] = existing_tip
            logger.debug(
                f"Collected existing tip for {match_id}: {existing_tip}")

    def _get_tip_value(self, home_field, away_field) -> Optional[tuple]:
        home_value = SeleniumUtils.safe_get_attribute(
            home_field, 'value', 'home tip field') or ''
        away_value = SeleniumUtils.safe_get_attribute(
            away_field, 'value', 'away tip field') or ''

        if not home_value.strip() or not away_value.strip():
            return None

        try:
            return int(home_value), int(away_value)
        except ValueError:
            logger.debug(
                f"Could not parse existing tip values: '{home_value}', '{away_value}'")
            return None

    def _reset_state(self) -> None:
        """Reset processing state for a new run."""
        self.last_seen_time = None
        self.processed_count = 0
        self.game_number = 0
        logger.debug("Reset processing state")

    def _update_last_seen_time(self, new_time: datetime, source: str) -> None:
        """Update the last seen time and log the change."""
        self.last_seen_time = new_time
        logger.debug(
            f"Updated time from {source}: {self.last_seen_time.strftime('%d.%m.%y %H:%M')}")

    def _get_games_count(self) -> int:
        """Get the number of games available for tipping."""
        logger.debug("Counting available games")

        # Try to find the games table first
        table = SeleniumUtils.safe_find_element(
            self.driver, By.ID, "tippabgabeSpiele")
        if not table:
            logger.warning("Could not find tipping table (tippabgabeSpiele)")
            return 0

        # Count only datarow elements (actual games, not rowheaders)
        games = SeleniumUtils.safe_find_elements(
            self.driver, By.XPATH, '//*[@id="tippabgabeSpiele"]/tbody/tr[contains(@class, "datarow")]')
        count = len(games)
        logger.debug(f"Found {count} game rows with class 'datarow'")

        # If no datarow elements, try alternative selectors
        if count == 0:
            logger.debug(
                "No 'datarow' elements found, trying alternative selectors")
            # Try finding table rows in the tipping table
            table_rows = SeleniumUtils.safe_find_elements(
                self.driver, By.XPATH, '//*[@id="tippabgabeSpiele"]//tr')
            logger.debug(f"Found {len(table_rows)} total table rows")

            # Filter out header rows (usually first row)
            if len(table_rows) > 1:
                count = len(table_rows) - 1  # Subtract header row
                logger.debug(f"Adjusted count after removing header: {count}")

        return count

    def _process_all_table_rows(self) -> int:
        """Process all table rows sequentially, maintaining time state."""
        logger.debug("Processing table rows sequentially")

        all_rows = self.table_processor.get_all_table_rows()
        if not all_rows:
            logger.warning("No table rows found")
            return 0

        for row_index, _ in enumerate(all_rows):
            try:
                row, row_class = self.table_processor.get_row_safely(
                    all_rows, row_index)
                if row is None or row_class is None:
                    continue

                if 'rowheader' in row_class:
                    self._process_rowheader(row, row_index)
                elif 'datarow' in row_class:
                    self._process_datarow_wrapper(row, row_index)

            except Exception as e:
                logger.error(f"Error processing table row {row_index}: {e}")
                continue

        logger.info(f"Processed {self.processed_count} games successfully")
        return self.processed_count

    def _process_rowheader(self, row, row_index: int) -> None:
        """Process a rowheader row to extract time information."""
        logger.debug(f"Found rowheader row {row_index}")
        extracted_time = TimeExtractor.extract_from_rowheader(row)
        if extracted_time:
            self._update_last_seen_time(extracted_time, "rowheader")
        else:
            logger.debug("Could not extract time from rowheader")

    def _process_datarow_wrapper(self, row, row_index: int) -> None:
        """Process a datarow wrapper that handles time state management."""
        self.game_number += 1
        logger.debug(
            f"Processing datarow {self.game_number} (row {row_index}), "
            f"last_seen_time: {self.last_seen_time.strftime('%d.%m.%y %H:%M') if self.last_seen_time else 'None'}")

        # Get time for this game
        game_time = TimeExtractor.extract_from_datarow(
            row, self.last_seen_time)

        # Update last_seen_time if we found a visible time in this datarow
        if TimeExtractor.has_visible_time(row):
            self._update_last_seen_time(game_time, "datarow")

        # Process the actual game
        if self._process_datarow(self.game_number, row, game_time):
            self.processed_count += 1

    def _process_datarow(self, game_number: int, data_row, game_time: datetime) -> bool:
        """Process a single game datarow."""
        try:
            # Extract team names using the extractor
            home_team = GameDataExtractor.extract_team_name(
                data_row, 2, 'home')
            away_team = GameDataExtractor.extract_team_name(
                data_row, 3, 'away')

            if not home_team or not away_team:
                logger.warning(
                    f"Could not extract team names for game {game_number}")
                return False

            logger.info(
                f"Processing: {home_team} vs {away_team} | Time: {game_time.strftime('%d.%m.%y %H:%M')}")


            # Check if the game has already started (timezone-safe, zoneinfo)  
            now_berlin = datetime.now(ZoneInfo('Europe/Berlin'))
            if game_time <= now_berlin:
                logger.info(f"Game {game_number} has already started ({game_time.strftime('%d.%m.%y %H:%M %z')}). Skipping...")
                return False

            # Get tip fields using the new extractor
            tip_fields = GameDataExtractor.get_tip_fields(data_row)
            if not tip_fields:
                logger.debug(
                    f"Game {game_number} cannot be tipped (likely finished)")
                return False

            home_tip_field, away_tip_field = tip_fields

            # Check if already tipped
            if not Config.OVERWRITE_TIPS() and self._is_already_tipped(home_tip_field, away_tip_field):
                home_val = SeleniumUtils.safe_get_attribute(
                    home_tip_field, 'value', 'home tip field') or ''
                away_val = SeleniumUtils.safe_get_attribute(
                    away_tip_field, 'value', 'away tip field') or ''
                logger.info(f"Game already tipped: {home_val} - {away_val}")
                return False

            # Extract quotes using the new extractor (may be empty for AI predictor)
            quotes = GameDataExtractor.extract_quotes(data_row) or []
            logger.debug(f"Quotes: {quotes}")

            # Create game object
            game = Game(home_team, away_team, quotes, game_time)

            # Build a stable match id
            match_id = f"{home_team}|{away_team}|{game_time.isoformat()}"
            tip_prediction_method = None

            # Use an existing tip from any scanned competition if available
            if match_id in self.existing_tips:
                tip = self.existing_tips[match_id]
                tip_prediction_method = 'existing-bet'
            elif match_id in self.predictions_cache:
                tip = self.predictions_cache[match_id]
                tip_prediction_method = 'cached'
            else:
                predictor = get_predictor()
                tip = None
                prediction_method = Config.PREDICTOR()
                try:
                    tip = predictor.predict(game, self.current_competition or '')
                    if not self._is_valid_tip(tip):
                        raise ValueError(f"Predictor returned invalid tip: {tip}")
                    self.predictions_cache[match_id] = tip
                    tip_prediction_method = prediction_method
                except Exception as e:
                    logger.warning(
                        "Predictor %s failed for %s vs %s: %s",
                        predictor.__class__.__name__,
                        home_team,
                        away_team,
                        e
                    )
                    if Config.PREDICTOR() == 'ai':
                        try:
                            fallback_predictor = QuotesPredictor()
                            tip = fallback_predictor.predict(game, self.current_competition or '')
                            if not self._is_valid_tip(tip):
                                raise ValueError(f"Fallback predictor returned invalid tip: {tip}")
                            tip_prediction_method = 'quotes-fallback'
                            self.predictions_cache[match_id] = tip
                            logger.info(
                                "AI predictor failed; falling back to quote-based predictor for %s vs %s: %s - %s",
                                home_team,
                                away_team,
                                tip[0],
                                tip[1]
                            )
                        except Exception as fallback_exc:
                            logger.error(
                                "AI predictor failed and quote fallback also failed for %s vs %s: %s",
                                home_team,
                                away_team,
                                fallback_exc
                            )
                            try:
                                self.notification_manager.send_all_notifications(
                                    game_time,
                                    home_team,
                                    away_team,
                                    quotes,
                                    (None, None),
                                    self.current_competition or '',
                                    prediction_method='ai+quotes-fallback',
                                    prediction_error=str(fallback_exc)
                                )
                            except Exception:
                                pass
                            return False
                    else:
                        logger.error(
                            "Predictor failed for %s vs %s and no fallback configured: %s",
                            home_team,
                            away_team,
                            e
                        )
                        try:
                            self.notification_manager.send_all_notifications(
                                game_time,
                                home_team,
                                away_team,
                                quotes,
                                (None, None),
                                self.current_competition or '',
                                prediction_method=Config.PREDICTOR(),
                                prediction_error=str(e)
                            )
                        except Exception:
                            pass
                        return False

            # Check timing constraints unless we are copying an existing bet
            if tip_prediction_method != 'existing-bet' and not self._should_tip_game(game_time):
                return False
                predictor = get_predictor()
                tip = None
                prediction_method = Config.PREDICTOR()
                try:
                    tip = predictor.predict(game, self.current_competition or '')
                    if not self._is_valid_tip(tip):
                        raise ValueError(f"Predictor returned invalid tip: {tip}")
                    self.predictions_cache[match_id] = tip
                    tip_prediction_method = prediction_method
                except Exception as e:
                    logger.warning(
                        "Predictor %s failed for %s vs %s: %s",
                        predictor.__class__.__name__,
                        home_team,
                        away_team,
                        e
                    )
                    if Config.PREDICTOR() == 'ai':
                        try:
                            fallback_predictor = QuotesPredictor()
                            tip = fallback_predictor.predict(game, self.current_competition or '')
                            if not self._is_valid_tip(tip):
                                raise ValueError(f"Fallback predictor returned invalid tip: {tip}")
                            tip_prediction_method = 'quotes-fallback'
                            self.predictions_cache[match_id] = tip
                            logger.info(
                                "AI predictor failed; falling back to quote-based predictor for %s vs %s: %s - %s",
                                home_team,
                                away_team,
                                tip[0],
                                tip[1]
                            )
                        except Exception as fallback_exc:
                            logger.error(
                                "AI predictor failed and quote fallback also failed for %s vs %s: %s",
                                home_team,
                                away_team,
                                fallback_exc
                            )
                            try:
                                self.notification_manager.send_all_notifications(
                                    game_time,
                                    home_team,
                                    away_team,
                                    quotes,
                                    (None, None),
                                    self.current_competition or '',
                                    prediction_method='ai+quotes-fallback',
                                    prediction_error=str(fallback_exc)
                                )
                            except Exception:
                                pass
                            return False
                    else:
                        logger.error(
                            "Predictor failed for %s vs %s and no fallback configured: %s",
                            home_team,
                            away_team,
                            e
                        )
                        try:
                            self.notification_manager.send_all_notifications(
                                game_time,
                                home_team,
                                away_team,
                                quotes,
                                (None, None),
                                self.current_competition or '',
                                prediction_method=Config.PREDICTOR(),
                                prediction_error=str(e)
                            )
                        except Exception:
                            pass
                        return False

            if not self._is_valid_tip(tip):
                logger.error("Invalid tip generated for %s vs %s: %s", home_team, away_team, tip)
                try:
                    self.notification_manager.send_all_notifications(
                        game_time,
                        home_team,
                        away_team,
                        quotes,
                        (None, None),
                        self.current_competition or '',
                        prediction_method=tip_prediction_method or Config.PREDICTOR(),
                        prediction_error=f"Invalid tip generated: {tip}"
                    )
                except Exception:
                    pass
                return False

            logger.info("Calculated tip using %s predictor: %s - %s", tip_prediction_method, tip[0], tip[1])

            # Enter tip and send notifications
            if self._enter_tip(home_tip_field, away_tip_field, tip):
                try:
                    # Pass competition information
                    competition = self.current_competition or ''
                    self.notification_manager.send_all_notifications(
                        game_time,
                        home_team,
                        away_team,
                        quotes,
                        tip,
                        competition,
                        prediction_method=tip_prediction_method,
                        prediction_error=''
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to send notifications for game {game_number}: {e}")
                return True
            else:
                logger.error(f"Failed to enter tip for game {game_number}")
                return False

        except Exception as e:
            logger.error(f"Error processing game {game_number}: {e}")
            return False

    def _is_already_tipped(self, home_field, away_field) -> bool:
        """Check if the game has already been tipped."""
        home_value = SeleniumUtils.safe_get_attribute(
            home_field, 'value', 'home tip field') or ''
        away_value = SeleniumUtils.safe_get_attribute(
            away_field, 'value', 'away tip field') or ''
        return bool(home_value and away_value)

    def _should_tip_game(self, game_time: datetime) -> bool:
        """Check if the game should be tipped based on timing."""
        time_until_game = game_time - datetime.now(ZoneInfo('Europe/Berlin'))
        logger.debug(f"Time until game: {time_until_game}")

        if time_until_game > Config.TIME_UNTIL_GAME():
            logger.info(
                f"Game starts in more than {Config.TIME_UNTIL_GAME()}. Skipping...")
            return False

        logger.info(
            f"Game starts in less than {Config.TIME_UNTIL_GAME()}. Proceeding with tip...")
        return True

    def _enter_tip(self, home_field, away_field, tip: tuple) -> bool:
        """
        Enter the calculated tip into the form fields.

        Returns:
            True if successful, False otherwise
        """
        try:
            # Enter home team tip
            if not SeleniumUtils.safe_send_keys(home_field, str(tip[0]), "home tip field"):
                logger.error("Failed to enter home team tip")
                return False

            # Enter away team tip
            if not SeleniumUtils.safe_send_keys(away_field, str(tip[1]), "away tip field"):
                logger.error("Failed to enter away team tip")
                return False

            logger.info(f"Successfully entered tip: {tip[0]} - {tip[1]}")
            return True

        except Exception as e:
            logger.error(f"Unexpected error entering tip: {e}")
            return False

    def _submit_all_tips(self) -> None:
        """Submit all entered tips."""
        logger.info("Submitting tips form")

        # Wait a moment for any dynamic updates to the form
        sleep(1)

        submit_button = SeleniumUtils.safe_find_element(
            self.driver, By.NAME, "submitbutton")
        if not submit_button:
            logger.error(
                "Could not find submit button with name 'submitbutton'")
            raise GameTippingError("Submit button not found")

        logger.debug("Found submit button, attempting to click")

        # Try to scroll the button into view first
        try:
            self.driver.execute_script(
                "arguments[0].scrollIntoView(true);", submit_button)
            sleep(0.5)  # Brief pause after scrolling
            logger.debug("Scrolled submit button into view")
        except Exception as e:
            logger.debug(f"Could not scroll to submit button: {e}")

        # Try regular click first
        if SeleniumUtils.safe_click(submit_button, "submit button"):
            logger.info("Tips form submitted successfully")
        else:
            # Fallback to JavaScript click
            logger.info("Regular click failed, trying JavaScript click")
            try:
                self.driver.execute_script(
                    "arguments[0].click();", submit_button)
                logger.info("Tips form submitted successfully via JavaScript")
            except Exception as e:
                logger.error(f"Both regular and JavaScript clicks failed: {e}")
                raise GameTippingError("Failed to submit tips form")

    def _is_debug_mode(self) -> bool:
        """Check if running in debug mode."""
        try:
            return len(sys.argv) > 1 and '--debug' in sys.argv
        except IndexError:
            return False

    def _accept_terms_and_conditions(self) -> None:
        """Accept terms and conditions if the dialog appears on the tipping page."""
        logger.debug("Checking for terms and conditions dialog")

        # Look for SourcePoint iframe (where the terms dialog actually is)
        iframe = SeleniumUtils.safe_find_element(
            self.driver,
            By.CSS_SELECTOR,
            'iframe[id*="sp_message_iframe"]',
            timeout=3
        )

        if iframe:
            try:
                # Switch to iframe and find accept button
                self.driver.switch_to.frame(iframe)
                sleep(1)  # Brief wait for iframe content

                accept_button = SeleniumUtils.safe_find_element(
                    self.driver,
                    By.XPATH,
                    '//button[contains(text(), "Akzeptieren")]',
                    timeout=2
                )

                if accept_button and SeleniumUtils.safe_click(accept_button, "terms accept button"):
                    logger.info("Terms and conditions accepted successfully")

                # Always switch back to main content
                self.driver.switch_to.default_content()

            except Exception as e:
                logger.warning(f"Error handling terms dialog: {e}")
