import os
import asyncio
import logging
import base64
from dotenv import load_dotenv
import httpx
import tweepy
import telegram
from PIL import Image
import cloudinary
import cloudinary.uploader

# --- Global Configuration from Environment Variables ---
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Twitter (V2 for posting, V1.1 for media upload)
TWITTER_CLIENT_ID = os.getenv("TWITTER_CLIENT_ID")
TWITTER_CLIENT_SECRET = os.getenv("TWITTER_CLIENT_SECRET")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_REFRESH_TOKEN = os.getenv("TWITTER_REFRESH_TOKEN")
TWITTER_API_KEY_V1 = os.getenv("TWITTER_API_KEY_V1")
TWITTER_API_SECRET_V1 = os.getenv("TWITTER_API_SECRET_V1")
TWITTER_ACCESS_TOKEN_V1 = os.getenv("TWITTER_ACCESS_TOKEN_V1")
TWITTER_ACCESS_TOKEN_SECRET_V1 = os.getenv("TWITTER_ACCESS_TOKEN_SECRET_V1")

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")

# Instagram (and Facebook Page)
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
IG_PAGE_ID = os.getenv("IG_PAGE_ID")
IG_ACCOUNT_ID = os.getenv("IG_ACCOUNT_ID")

# Cloudinary configuration
CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")

# Global instances (to avoid re-initialization)
twitter_v1_api = None

if all([CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET]):
    cloudinary.config(
        cloud_name=CLOUDINARY_CLOUD_NAME,
        api_key=CLOUDINARY_API_KEY,
        api_secret=CLOUDINARY_API_SECRET
    )
    logger.info("☁️ Cloudinary configured.")
else:
    logger.warning("⚠️ Cloudinary credentials not fully set. Image uploads to Cloudinary will be skipped for Instagram/Facebook posts.")

# --- Twitter Posting Functions ---

async def post_to_twitter(caption: str, image_path: str = None):
    """Posts a text tweet or an image tweet to Twitter."""
    global twitter_v1_api
    if not all([TWITTER_CLIENT_ID, TWITTER_CLIENT_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_REFRESH_TOKEN, TWITTER_API_KEY_V1,
                 TWITTER_API_SECRET_V1, TWITTER_ACCESS_TOKEN_V1, TWITTER_ACCESS_TOKEN_SECRET_V1]):
        logger.error("❌ One or more Twitter API credentials are not set. Skipping Twitter post.")
        return

    try:
        # Initialize Tweepy V2 Client for posting tweets
        client_v2 = tweepy.Client(
            bearer_token=os.getenv("TWITTER_BEARER_TOKEN"),
            consumer_key=TWITTER_API_KEY_V1,  # Use v1 keys for client authentication
            consumer_secret=TWITTER_API_SECRET_V1,
            access_token=TWITTER_ACCESS_TOKEN_V1,
            access_token_secret=TWITTER_ACCESS_TOKEN_SECRET_V1
        )

        media_ids = []
        if image_path and os.path.exists(image_path):
            logger.info("🐦 Uploading image to Twitter media endpoint using V1.1 API...")
            
            # Use Tweepy V1.1 API for media upload
            auth_v1 = tweepy.OAuth1UserHandler(
                TWITTER_API_KEY_V1, TWITTER_API_SECRET_V1, TWITTER_ACCESS_TOKEN_V1, TWITTER_ACCESS_TOKEN_SECRET_V1
            )
            api_v1 = tweepy.API(auth_v1)
            
            media = await asyncio.to_thread(api_v1.media_upload, filename=image_path)
            media_ids.append(media.media_id_string)
            logger.info("✅ Image uploaded to Twitter media. Media ID: %s", media.media_id_string)

        # Post the tweet using the V2 client and the V1.1 media ID
        tweet_response = await asyncio.to_thread(client_v2.create_tweet, text=caption, media_ids=media_ids)
        logger.info("✅ Successfully posted to Twitter! Tweet ID: %s", tweet_response.data['id'])

    except tweepy.HTTPException as e:
        if e.response.status_code == 401:
            logger.info("🔄 Twitter Access Token unauthorized. Attempting to refresh token...")
            new_access_token = await refresh_twitter_token()
            if new_access_token:
                await post_to_twitter(caption, image_path)
            else:
                logger.error("❌ Failed to refresh Twitter token. Please regenerate tokens.")
        else:
            logger.error("❌ Twitter post failed: %s - Response: %s", e.response.status_code, e.response.text)
    except Exception as e:
        logger.error("Unexpected error while posting to Twitter: %s", e)

# --- Instagram Posting Functions ---

async def post_to_instagram_feed(image_url: str, caption: str):
    """Posts an image with a caption to Instagram Feed."""
    if not all([IG_ACCOUNT_ID, IG_ACCESS_TOKEN]):
        logger.error("❌ Instagram Account ID or Access Token not set. Cannot post to Instagram Feed.")
        return
    try:
        container_url = f"https://graph.facebook.com/v19.0/{IG_ACCOUNT_ID}/media"
        publish_url = f"https://graph.facebook.com/v19.0/{IG_ACCOUNT_ID}/media_publish"
        async with httpx.AsyncClient(timeout=30.0) as client:
            container_response = await client.post(container_url, data={
                "image_url": image_url,
                "caption": caption,
                "access_token": IG_ACCESS_TOKEN
            })
            container_data = container_response.json()
            if 'id' in container_data:
                container_id = container_data['id']
                publish_response = await client.post(publish_url, data={
                    "creation_id": container_id,
                    "access_token": IG_ACCESS_TOKEN
                })
                publish_data = publish_response.json()
                if 'id' in publish_data:
                    logger.info("✅ Successfully posted to Instagram Feed! Post ID: %s", publish_data['id'])
                else:
                    logger.error("❌ Instagram Feed publish failed: %s", publish_data)
            else:
                logger.error("❌ Failed to create IG Feed media container. Error: %s", container_data.get('error', 'Unknown error'))
    except httpx.HTTPStatusError as e:
        logger.exception("Instagram Feed HTTP error: %s - Response: %s", e.response.status_code, e.response.text)
    except Exception as e:
        logger.exception("An unexpected error occurred while posting to Instagram Feed:")

async def post_to_instagram_story(image_url: str):
    """Posts an image to Instagram Stories."""
    if not all([IG_ACCOUNT_ID, IG_ACCESS_TOKEN]):
        logger.error("❌ Instagram Account ID or Access Token not set. Cannot post to Instagram Story.")
        return
    try:
        container_url = f"https://graph.facebook.com/v19.0/{IG_ACCOUNT_ID}/media"
        publish_url = f"https://graph.facebook.com/v19.0/{IG_ACCOUNT_ID}/media_publish"
        async with httpx.AsyncClient(timeout=30.0) as client:
            container_response = await client.post(container_url, data={
                "image_url": image_url,
                "media_type": "STORIES",
                "access_token": IG_ACCESS_TOKEN
            })
            container_data = container_response.json()
            if 'id' in container_data:
                container_id = container_data['id']
                publish_response = await client.post(publish_url, data={
                    "creation_id": container_id,
                    "access_token": IG_ACCESS_TOKEN
                })
                publish_data = publish_response.json()
                if 'id' in publish_data:
                    logger.info("✅ Successfully posted to Instagram Story! Story ID: %s", publish_data['id'])
                else:
                    logger.error("❌ Instagram Story publish failed: %s", publish_data)
            else:
                logger.error("❌ Failed to create IG Story media container. Error: %s", container_data.get('error', 'Unknown error'))
    except httpx.HTTPStatusError as e:
        logger.exception("Instagram Story HTTP error: %s - Response: %s", e.response.status_code, e.response.text)
    except Exception as e:
        logger.exception("An unexpected error occurred while posting to Instagram Story:")

# --- Telegram Channel Posting ---

async def post_to_telegram_channel(image_path: str, caption: str, bot_instance: telegram.Bot):
    """Posts an image with a caption to a specified Telegram channel."""
    if not TELEGRAM_CHANNEL_ID:
        logger.error("❌ TELEGRAM_CHANNEL_ID is not set. Cannot post to Telegram channel.")
        return
    try:
        logger.info("✈️ Posting to Telegram channel %s...", TELEGRAM_CHANNEL_ID)
        with open(image_path, 'rb') as photo_file:
            await bot_instance.send_photo(chat_id=TELEGRAM_CHANNEL_ID, photo=photo_file, caption=caption)
        logger.info("✅ Successfully posted to Telegram channel!")
    except Exception as e:
        logger.exception("❌ Error posting to Telegram channel:")

async def post_text_to_telegram_channel(text: str, bot_instance: telegram.Bot):
    """Posts a text message to a specified Telegram channel."""
    if not TELEGRAM_CHANNEL_ID:
        logger.error("❌ TELEGRAM_CHANNEL_ID is not set. Skipping text post to Telegram channel.")
        return
    try:
        logger.info("✈️ Posting text to Telegram channel %s...", TELEGRAM_CHANNEL_ID)
        await bot_instance.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=text)
        logger.info("✅ Successfully posted text to Telegram channel!")
    except Exception as e:
        logger.exception("❌ Error posting text to Telegram channel:")

# --- Telegram Bot Message Handler ---

async def handle_telegram_message(update: telegram.Update, bot_instance: telegram.Bot):
    """Handles incoming messages from Telegram and distributes to all social media platforms."""
    image_path = None
    try:
        if not update.message:
            logger.warning("Received update without a message object.")
            return

        message = update.message
        logger.info("Received message from %s: %s", message.chat.username, message.text or "No text (likely a photo)")
        caption = message.caption or message.text or "No caption"

        posting_tasks = []

        if message.photo:
            file_id = message.photo[-1].file_id
            file_obj = await bot_instance.get_file(file_id)
            image_path = os.path.join(os.getcwd(), f"temp_{file_id}.jpg")
            await file_obj.download_to_drive(image_path)
            logger.info("📥 Photo downloaded to %s", image_path)

            is_feed_compatible = False
            cloudinary_image_url = None

            if os.path.exists(image_path):
                # Check image dimensions for Instagram Feed
                try:
                    with Image.open(image_path) as img:
                        width, height = img.size
                        aspect_ratio = width / height
                        is_feed_compatible = (0.8 <= aspect_ratio <= 1.91)
                        logger.info("Image dimensions: %dx%d, Aspect Ratio: %.2f. Feed compatible: %s", width, height, aspect_ratio, is_feed_compatible)
                except Exception as e:
                    logger.exception("Error checking image aspect ratio. Assuming not feed compatible.")

                # Upload to Cloudinary if configured
                if CLOUDINARY_CLOUD_NAME:
                    try:
                        result = await asyncio.to_thread(cloudinary.uploader.upload, image_path)
                        cloudinary_image_url = result['secure_url']
                        logger.info("☁️ Uploaded to Cloudinary: %s", cloudinary_image_url)
                    except Exception as e:
                        logger.exception("❌ Failed to upload image to Cloudinary.")

            # Post to all relevant platforms based on media and configuration
            posting_tasks.append(post_to_twitter(caption, image_path))
            posting_tasks.append(post_to_telegram_channel(image_path, caption, bot_instance))

            if cloudinary_image_url:
                if is_feed_compatible:
                    posting_tasks.append(post_to_instagram_feed(cloudinary_image_url, caption))
                else:
                    logger.info("Image not compatible with Instagram Feed. Skipping.")
                posting_tasks.append(post_to_instagram_story(cloudinary_image_url))

        elif message.text:
            posting_tasks.append(post_to_twitter(message.text))
            posting_tasks.append(post_text_to_telegram_channel(message.text, bot_instance))
            logger.info("Skipping Instagram/Facebook posts for text-only message.")

        if posting_tasks:
            await asyncio.gather(*posting_tasks)
            await message.reply_text("✅ Your post has been sent to all configured social media platforms!")
        else:
            await message.reply_text("❌ No posting tasks were executed. Please check the logs for errors.")

    except Exception as e:
        logger.exception("Error handling Telegram message:")
        if update.message:
            await update.message.reply_text("❌ Failed to process your request and post the content. Please check logs for details.")
    finally:
        if image_path and os.path.exists(image_path):
            os.remove(image_path)
            logger.info("🗑️ Cleaned up temporary file: %s", image_path)

# --- Main Bot Function ---

async def main():
    """Initializes and runs the Telegram bot to handle messages and post to social media."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN is not set. Exiting.")
        return

    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
    try:
        bot_info = await bot.get_me()
        logger.info("🚀 Telegram Bot is running as @%s.", bot_info.username)
        await bot.delete_webhook()
        logger.info("Webhook deleted to ensure polling mode.")
    except telegram.error.InvalidToken:
        logger.error("❌ Invalid Telegram Bot Token. Please check your .env file.")
        return
    except Exception as e:
        logger.error("❌ Error during bot initialization: %s", e)
        return

    update_id = 0
    while True:
        try:
            updates = await bot.get_updates(offset=update_id, timeout=10)
            for update in updates:
                if update.update_id >= update_id:
                    update_id = update.update_id + 1
                    await handle_telegram_message(update, bot)
            await asyncio.sleep(1)
        except telegram.error.TimedOut:
            pass
        except telegram.error.NetworkError as e:
            logger.error("Telegram Network Error: %s. Retrying in 5 seconds...", e)
            await asyncio.sleep(5)
        except Exception as e:
            logger.error("Error in main loop: %s. Retrying in 5 seconds...", e)
            await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    except Exception as e:
        logger.exception("An unhandled error occurred in the main execution:")