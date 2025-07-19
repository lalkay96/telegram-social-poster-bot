import os
import asyncio
import logging
from dotenv import load_dotenv
import httpx
import base64
import tweepy
import telegram

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Global variables
twitter_v1_api = None
TWITTER_CLIENT_ID = os.getenv("TWITTER_CLIENT_ID")
TWITTER_CLIENT_SECRET = os.getenv("TWITTER_CLIENT_SECRET")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_REFRESH_TOKEN = os.getenv("TWITTER_REFRESH_TOKEN")
TWITTER_API_KEY_V1 = os.getenv("TWITTER_API_KEY_V1")
TWITTER_API_SECRET_V1 = os.getenv("TWITTER_API_SECRET_V1")
TWITTER_ACCESS_TOKEN_V1 = os.getenv("TWITTER_ACCESS_TOKEN_V1")
TWITTER_ACCESS_TOKEN_SECRET_V1 = os.getenv("TWITTER_ACCESS_TOKEN_SECRET_V1")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
IG_PAGE_ID = os.getenv("IG_PAGE_ID")
IG_ACCOUNT_ID = os.getenv("IG_ACCOUNT_ID")

async def refresh_twitter_token():
    try:
        async with httpx.AsyncClient() as client:
            auth_header = base64.b64encode(f"{TWITTER_CLIENT_ID}:{TWITTER_CLIENT_SECRET}".encode()).decode()
            response = await client.post(
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
            logger.warning("🔑 Twitter tokens refreshed! PLEASE UPDATE YOUR .ENV FILE:")
            logger.warning("TWITTER_ACCESS_TOKEN=%s", new_access_token)
            logger.warning("TWITTER_REFRESH_TOKEN=%s", new_refresh_token)
            return new_access_token
    except httpx.HTTPStatusError as e:
        logger.error("Failed to refresh Twitter token: %s - Response: %s", e.response.status_code, e.response.text)
        return None
    except Exception as e:
        logger.error("Unexpected error while refreshing Twitter token: %s", e)

async def post_to_twitter(caption: str, image_path: str = None):
    global twitter_v1_api
    logger.info("Twitter Env Vars Loaded: CLIENT_ID=%s, ACCESS_TOKEN=%s, REFRESH_TOKEN=%s, API_KEY_V1=%s",
                TWITTER_CLIENT_ID, "*" * len(TWITTER_ACCESS_TOKEN or ""),
                "*" * len(TWITTER_REFRESH_TOKEN or ""), TWITTER_API_KEY_V1)

    if not all([TWITTER_CLIENT_ID, TWITTER_ACCESS_TOKEN, TWITTER_REFRESH_TOKEN,
                TWITTER_API_KEY_V1, TWITTER_API_SECRET_V1, TWITTER_ACCESS_TOKEN_V1, TWITTER_ACCESS_TOKEN_SECRET_V1]):
        logger.error("❌ One or more Twitter API credentials are not set. Please check your .env file.")
        return

    try:
        if twitter_v1_api is None:
            try:
                auth_v1 = tweepy.OAuth1UserHandler(
                    TWITTER_API_KEY_V1, TWITTER_API_SECRET_V1,
                    TWITTER_ACCESS_TOKEN_V1, TWITTER_ACCESS_TOKEN_SECRET_V1
                )
                twitter_v1_api = tweepy.API(auth_v1)
                logger.info("🐦 Initialized Tweepy v1.1 API for media upload.")
            except NameError:
                logger.error("❌ Tweepy module not found. Please install it with 'pip install tweepy'.")
                return

        media_ids = []
        if image_path and os.path.exists(image_path):
            logger.info("🐦 Uploading image to Twitter media endpoint: %s", image_path)
            media = await asyncio.to_thread(twitter_v1_api.media_upload, filename=image_path)
            media_ids.append(media.media_id_string)
            logger.info("✅ Image uploaded to Twitter media. Media ID: %s", media.media_id_string)

        async with httpx.AsyncClient() as client:
            logger.info("🐦 Attempting to post to Twitter with caption: '%s' and media_ids: %s", caption, media_ids)
            payload = {"text": caption}
            if media_ids:
                payload["media"] = {"media_ids": media_ids}
            response = await client.post(
                "https://api.twitter.com/2/tweets",
                headers={"Authorization": f"Bearer {TWITTER_ACCESS_TOKEN}"},
                json=payload
            )
            response.raise_for_status()
            logger.info("✅ Successfully posted to Twitter! Tweet ID: %s", response.json()['data']['id'])

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            logger.info("🔄 Twitter Access Token unauthorized. Attempting to refresh token...")
            new_access_token = await refresh_twitter_token()
            if new_access_token:
                try:
                    media_ids = []
                    if image_path and os.path.exists(image_path):
                        media = await asyncio.to_thread(twitter_v1_api.media_upload, filename=image_path)
                        media_ids.append(media.media_id_string)
                    async with httpx.AsyncClient() as client:
                        payload = {"text": caption}
                        if media_ids:
                            payload["media"] = {"media_ids": media_ids}
                        response = await client.post(
                            "https://api.twitter.com/2/tweets",
                            headers={"Authorization": f"Bearer {new_access_token}"},
                            json=payload
                        )
                        response.raise_for_status()
                        logger.info("✅ Successfully posted to Twitter after token refresh! Tweet ID: %s", response.json()['data']['id'])
                except httpx.HTTPStatusError as retry_e:
                    logger.error("❌ Twitter post failed even after token refresh: %s - Response: %s", retry_e.response.status_code, retry_e.response.text)
            else:
                logger.error("❌ Failed to refresh Twitter token. Please regenerate tokens in Twitter Developer Portal.")
        else:
            logger.error("❌ Twitter post failed: %s - Response: %s", e.response.status_code, e.response.text)
    except Exception as e:
        logger.error("Unexpected error while posting to Twitter: %s", e)

async def post_to_telegram_channel(caption: str, image_path: str = None):
    if not TELEGRAM_CHANNEL_ID:
        logger.error("❌ TELEGRAM_CHANNEL_ID not set in .env file.")
        return
    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
    try:
        if image_path and os.path.exists(image_path):
            logger.info("📤 Uploading image to Telegram channel: %s", image_path)
            with open(image_path, 'rb') as photo:
                await bot.send_photo(chat_id=TELEGRAM_CHANNEL_ID, photo=photo, caption=caption)
            logger.info("✅ Image and caption posted to Telegram channel.")
        else:
            logger.info("📝 Posting caption to Telegram channel: %s", caption)
            await bot.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=caption)
            logger.info("✅ Caption posted to Telegram channel.")
    except Exception as e:
        logger.error("❌ Failed to post to Telegram channel: %s", e)

async def post_to_instagram(caption: str, image_path: str = None):
    if not all([IG_ACCESS_TOKEN, IG_PAGE_ID, IG_ACCOUNT_ID]):
        logger.error("❌ Instagram credentials (access token, page ID, account ID) not set in .env file.")
        return

    try:
        async with httpx.AsyncClient() as client:
            if image_path and os.path.exists(image_path):
                # Upload image to Instagram Feed
                logger.info("📸 Uploading image to Instagram Feed: %s", image_path)
                with open(image_path, 'rb') as image_file:
                    files = {'image': (image_path, image_file, 'image/jpeg')}
                    response = await client.post(
                        f"https://graph.facebook.com/{IG_PAGE_ID}/media",
                        params={
                            "access_token": IG_ACCESS_TOKEN,
                            "caption": caption,
                            "image": image_path
                        },
                        files=files
                    )
                    response.raise_for_status()
                    creation_id = response.json()['id']
                    logger.info("✅ Image uploaded to Instagram media. Creation ID: %s", creation_id)

                    # Publish to Feed
                    publish_response = await client.post(
                        f"https://graph.facebook.com/{IG_PAGE_ID}/media_publish",
                        params={
                            "access_token": IG_ACCESS_TOKEN,
                            "creation_id": creation_id
                        }
                    )
                    publish_response.raise_for_status()
                    feed_id = publish_response.json()['id']
                    logger.info("✅ Posted to Instagram Feed. Post ID: %s", feed_id)

                    # Upload to Stories (if supported)
                    story_response = await client.post(
                        f"https://graph.facebook.com/{IG_ACCOUNT_ID}/media_publish",
                        params={
                            "access_token": IG_ACCESS_TOKEN,
                            "creation_id": creation_id,
                            "story": "true"
                        }
                    )
                    story_response.raise_for_status()
                    story_id = story_response.json()['id']
                    logger.info("✅ Posted to Instagram Stories. Story ID: %s", story_id)
            else:
                logger.warning("📸 No image to post to Instagram. Caption-only posts are not supported.")
    except httpx.HTTPStatusError as e:
        logger.error("❌ Failed to post to Instagram: %s - Response: %s", e.response.status_code, e.response.text)
    except Exception as e:
        logger.error("Unexpected error while posting to Instagram: %s", e)

async def handle_telegram_message(update):
    if not update.message:
        logger.warning("Received update with no message attribute: %s", update)
        return
    message = update.message
    logger.info("Received message from %s: %s", message.chat.username, message.text or "No text (likely a photo)")

    if message.photo:
        file_id = message.photo[-1].file_id
        async with httpx.AsyncClient() as client:
            file_response = await client.get(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile?file_id={file_id}"
            )
            file_response.raise_for_status()
            file_path = file_response.json()["result"]["file_path"]
            photo_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
            photo_response = await client.get(photo_url)
            photo_response.raise_for_status()
            image_path = os.path.join(os.getcwd(), f"temp_{file_id}.jpg")
            with open(image_path, "wb") as f:
                f.write(photo_response.content)

        caption = message.caption or "Posted via @9jacashflowbot"
        await asyncio.gather(
            post_to_twitter(caption, image_path),
            post_to_telegram_channel(caption, image_path),
            post_to_instagram(caption, image_path)
        )
        os.remove(image_path)
    elif message.text:
        await asyncio.gather(
            post_to_twitter(message.text),
            post_to_telegram_channel(message.text)
        )
    else:
        logger.warning("Unsupported message type received.")

async def main():
    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
    update_id = 0

    while True:
        try:
            updates = await bot.get_updates(offset=update_id)
            logger.info("Received updates: %s", [u.to_dict() for u in updates])
            for update in updates:
                if update.update_id >= update_id:
                    update_id = update.update_id + 1
                    await handle_telegram_message(update)
            await asyncio.sleep(1)
        except Exception as e:
            logger.error("Error in main loop: %s", e)
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())