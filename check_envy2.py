import os
from dotenv import load_dotenv
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

logger.info("TWITTER_API_KEY_V1: %s", os.getenv("TWITTER_API_KEY_V1"))
logger.info("TWITTER_API_SECRET_V1: %s", "*" * len(os.getenv("TWITTER_API_SECRET_V1") or ""))
logger.info("TWITTER_ACCESS_TOKEN_V1: %s", os.getenv("TWITTER_ACCESS_TOKEN_V1"))
logger.info("TWITTER_ACCESS_TOKEN_SECRET_V1: %s", "*" * len(os.getenv("TWITTER_ACCESS_TOKEN_SECRET_V1") or ""))