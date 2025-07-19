import tweepy
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
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_REFRESH_TOKEN = os.getenv("TWITTER_REFRESH_TOKEN")
TWITTER_API_KEY_V1 = os.getenv("TWITTER_API_KEY_V1")
TWITTER_API_SECRET_V1 = os.getenv("TWITTER_API_SECRET_V1")
TWITTER_ACCESS_TOKEN_V1 = os.getenv("TWITTER_ACCESS_TOKEN_V1")
TWITTER_ACCESS_TOKEN_SECRET_V1 = os.getenv("TWITTER_ACCESS_TOKEN_SECRET_V1")

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
        os.environ["TWITTER_ACCESS_TOKEN"] = new_access_token
        os.environ["TWITTER_REFRESH_TOKEN"] = new_refresh_token
        logger.info("Successfully refreshed tokens:")
        logger.info("TWITTER_ACCESS_TOKEN=%s", new_access_token)
        logger.info("TWITTER_REFRESH_TOKEN=%s", new_refresh_token)
        logger.info("Update your .env file with these values.")
        return new_access_token
    except httpx.HTTPStatusError as e:
        logger.error("Failed to refresh token: %s - Response: %s", e.response.status_code, e.response.text)
        return None
    except Exception as e:
        logger.error("Unexpected error: %s", e)
        return None

# Test with httpx (GET /2/users/me)
try:
    logger.info("Testing authentication with httpx...")
    response = httpx.get(
        "https://api.twitter.com/2/users/me",
        headers={"Authorization": f"Bearer {TWITTER_ACCESS_TOKEN}"}
    )
    response.raise_for_status()
    logger.info("httpx authenticated successfully: %s", response.json())
except httpx.HTTPStatusError as e:
    logger.error("httpx authentication failed: %s - Response: %s", e.response.status_code, e.response.text)
    logger.info("Attempting to refresh token...")
    new_access_token = refresh_twitter_token()
    if new_access_token:
        try:
            logger.info("Retrying authentication with new token...")
            response = httpx.get(
                "https://api.twitter.com/2/users/me",
                headers={"Authorization": f"Bearer {new_access_token}"}
            )
            response.raise_for_status()
            logger.info("httpx authenticated successfully: %s", response.json())
        except httpx.HTTPStatusError as retry_e:
            logger.error("httpx retry failed: %s - Response: %s", retry_e.response.status_code, retry_e.response.text)
    else:
        logger.error("Token refresh failed. Regenerate tokens with get_twitter_tokens_grok.py.")
except Exception as e:
    logger.error("Unexpected httpx error: %s", e)

# Test with httpx (POST /2/tweets)
try:
    logger.info("Testing tweet post with httpx...")
    response = httpx.post(
        "https://api.twitter.com/2/tweets",
        headers={"Authorization": f"Bearer {TWITTER_ACCESS_TOKEN}"},
        json={"text": "Test tweet from httpx"}
    )
    response.raise_for_status()
    logger.info("httpx posted tweet successfully: %s", response.json())
except httpx.HTTPStatusError as e:
    logger.error("httpx tweet post failed: %s - Response: %s", e.response.status_code, e.response.text)
except Exception as e:
    logger.error("Unexpected httpx tweet post error: %s", e)

# Test with tweepy
try:
    logger.info("Testing authentication with tweepy...")
    twitter_v2_client = tweepy.Client(access_token=TWITTER_ACCESS_TOKEN)
    user = twitter_v2_client.get_me()
    logger.info("tweepy authenticated as: %s", user.data.username)
    response = twitter_v2_client.create_tweet(text="Test tweet from tweepy")
    logger.info("tweepy posted test tweet: %s", response.data['id'])
except tweepy.TweepyException as e:
    logger.error("tweepy error: %s", e)
    logger.error("Response details: %s", e.response.text if e.response else "No response details")
except Exception as e:
    logger.error("Unexpected tweepy error: %s", e)