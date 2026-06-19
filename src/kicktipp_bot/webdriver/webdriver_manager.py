"""WebDriver management module for browser automation."""

import logging
import sys

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.chrome.service import Service
import os

from ..config import Config

logger = logging.getLogger(__name__)


class WebDriverManager:
    """Manages WebDriver creation and configuration."""

    @staticmethod
    def create_driver() -> WebDriver:
        """Create and configure a WebDriver instance based on arguments and configuration."""
        # Check for custom chrome driver path
        chromedriver_path = Config.CHROMEDRIVER_PATH()
        # Prepare chrome options
        chrome_options = Options()
        # Prefer binary from config if set, otherwise detect common system path
        chrome_binary = Config.CHROME_BINARY_PATH() or ('/usr/bin/google-chrome' if os.path.exists('/usr/bin/google-chrome') else None)
        if chrome_binary:
            chrome_options.binary_location = chrome_binary
        # If custom chromedriver path provided, use Service to pass executable
        if chromedriver_path is not None:
            logger.info('Using custom Chrome Driver path')
            service = Service(executable_path=chromedriver_path)
            return webdriver.Chrome(service=service, options=chrome_options)

        # Check for headless mode
        if WebDriverManager._is_headless_mode():
            logger.info('Running in headless mode')
            # merge our binary location into headless options
            headless_opts = WebDriverManager._get_headless_options()
            if getattr(chrome_options, 'binary_location', None):
                headless_opts.binary_location = chrome_options.binary_location
            return webdriver.Chrome(options=headless_opts)

        # Default mode: pass options (may include binary_location)
        return webdriver.Chrome(options=chrome_options)

    @staticmethod
    def _is_headless_mode() -> bool:
        """Check if the script should run in headless mode."""
        return len(sys.argv) > 1 and '--headless' in sys.argv

    @staticmethod
    def _get_headless_options() -> Options:
        """Configure Chrome options for headless browser operation."""
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-application-cache")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-setuid-sandbox")

        return chrome_options
