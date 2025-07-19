import httpx
import base64
import os
from dotenv import load_dotenv
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

TWITTER_CLIENT_ID = os.getenv("TWITTER_CLIENT_ID")
TWITTER_CLIENT_SECRET = os.getenv("TWITTER_CLIENT_SECRET")
TWITTER_REFRESH_TOKEN = os.getenv("TWITTER_REFRESH_TOKEN")

def refresh_twitter_token():
    try:
        auth_header = base64.b64encode(f"{TWITTER_CLIENT_ID}:{TWITTER_CLIENT_SECRET}".encode()).decode()
        response = httpx.post(
            "https://api.twitter.com/2/oauth2/token",
            headers={"Authorization": f"Basic {auth_header}"},
            data={
                "grant_type": "refresh_token",
                "refresh_token": TWITTER_REFRESH_TOKEN,
                "client_id": TWITTER_CLIENT_ID,
            }
        )
        response.raise_for_status()
        token_data = response.json()
        new_access_token = token_data["access_token"]
        new_refresh_token = token_data["refresh_token"]
        logger.info("Successfully refreshed tokens:")
        logger.info("TWITTER_ACCESS_TOKEN=%s", new_access_token)
        logger.info("TWITTER_REFRESH_TOKEN=%s", new_refresh_token)
        logger.info("Update your .env file with these values.")
        return new_access_token, new_refresh_token
    except httpx.HTTPStatusError as e:
        logger.error("Failed to refresh token: %s - Response: %s", e.response.status_code, e.response.text)
        return None, None
    except Exception as e:
        logger.error("Unexpected error: %s", e)
        return None, None

if __name__ == "__main__":
    if not all([TWITTER_CLIENT_ID, TWITTER_CLIENT_SECRET, TWITTER_REFRESH_TOKEN]):
        logger.error("Missing required environment variables.")
    else:
        refresh_twitter_token()