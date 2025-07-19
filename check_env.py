import os
from dotenv import load_dotenv
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

logger.info("TWITTER_CLIENT_ID: %s", os.getenv("TWITTER_CLIENT_ID"))
logger.info("TWITTER_CLIENT_SECRET: %s", "*" * len(os.getenv("TWITTER_CLIENT_SECRET") or ""))
logger.info("TWITTER_ACCESS_TOKEN: %s", "*" * len(os.getenv("TWITTER_ACCESS_TOKEN") or ""))
logger.info("TWITTER_REFRESH_TOKEN: %s", "*" * len(os.getenv("TWITTER_REFRESH_TOKEN") or ""))
logger.info("TWITTER_API_KEY_V1: %s", os.getenv("TWITTER_API_KEY_V1"))
logger.info("TWITTER_API_SECRET_V1: %s", "*" * len(os.getenv("TWITTER_API_SECRET_V1") or ""))
logger.info("TWITTER_ACCESS_TOKEN_V1: %s", os.getenv("TWITTER_ACCESS_TOKEN_V1"))
logger.info("TWITTER_ACCESS_TOKEN_SECRET_V1: %s", "*" * len(os.getenv("TWITTER_ACCESS_TOKEN_SECRET_V1") or ""))