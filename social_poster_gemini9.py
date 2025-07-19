import os
import asyncio
import logging
from dotenv import load_dotenv
import httpx
import base64
import tweepy
import telegram
from PIL import Image # Import Pillow for image dimension check
import cloudinary
import cloudinary.uploader

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# --- Global Configuration from Environment Variables ---
# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")

# Twitter API v2 OAuth 2.0 User Context credentials
TWITTER_CLIENT_ID = os.getenv("TWITTER_CLIENT_ID")
TWITTER_CLIENT_SECRET = os.getenv("TWITTER_CLIENT_SECRET")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_REFRESH_TOKEN = os.getenv("TWITTER_REFRESH_TOKEN")

# Twitter API v1.1 OAuth 1.0a User Context credentials (for media upload)
TWITTER_API_KEY_V1 = os.getenv("TWITTER_API_KEY_V1")
TWITTER_API_SECRET_V1 = os.getenv("TWITTER_API_SECRET_V1")
TWITTER_ACCESS_TOKEN_V1 = os.getenv("TWITTER_ACCESS_TOKEN_V1")
TWITTER_ACCESS_TOKEN_SECRET_V1 = os.getenv("TWITTER_ACCESS_TOKEN_SECRET_V1")

# Instagram (and Facebook Page)
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
IG_PAGE_ID = os.getenv("IG_PAGE_ID") # Facebook Page ID for posting to Facebook Page
IG_ACCOUNT_ID = os.getenv("IG_ACCOUNT_ID") # Instagram Business Account ID

# Cloudinary configuration
CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")

# Initialize Cloudinary
if all([CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET]):
    cloudinary.config(
        cloud_name=CLOUDINARY_CLOUD_NAME,
        api_key=CLOUDINARY_API_KEY,
        api_secret=CLOUDINARY_API_SECRET
    )
    logger.info("☁️ Cloudinary configured.")
else:
    logger.warning("⚠️ Cloudinary credentials not fully set. Image uploads to Cloudinary will be skipped.")

# Global tweepy API instance for v1.1 media uploads
twitter_v1_api = None

# --- Twitter Helper Functions ---

async def refresh_twitter_token():
    """Refreshes the Twitter OAuth 2.0 access token using the refresh token."""
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
            new_refresh_token = token_data.get("refresh_token", TWITTER_REFRESH_TOKEN) # Refresh token might not change
            
            # Update environment variables in memory
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
        return None

async def post_to_twitter(caption: str, image_path: str = None):
    """
    Posts a tweet with the given caption and optionally an image.
    Handles Twitter API v1.1 for media upload and v2 for tweet creation.
    """
    global twitter_v1_api

    # Log loaded environment variables (masked secrets)
    logger.info("Twitter Env Vars Loaded: CLIENT_ID=%s, CLIENT_SECRET=%s, ACCESS_TOKEN=%s, REFRESH_TOKEN=%s, API_KEY_V1=%s, API_SECRET_V1=%s, ACCESS_TOKEN_V1=%s, ACCESS_TOKEN_SECRET_V1=%s",
                TWITTER_CLIENT_ID,
                "*" * len(TWITTER_CLIENT_SECRET or ""),
                "*" * len(TWITTER_ACCESS_TOKEN or ""),
                "*" * len(TWITTER_REFRESH_TOKEN or ""),
                TWITTER_API_KEY_V1,
                "*" * len(TWITTER_API_SECRET_V1 or ""),
                "*" * len(TWITTER_ACCESS_TOKEN_V1 or ""),
                "*" * len(TWITTER_ACCESS_TOKEN_SECRET_V1 or ""))

    # Ensure all required Twitter credentials are set
    if not all([TWITTER_CLIENT_ID, TWITTER_CLIENT_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_REFRESH_TOKEN,
                TWITTER_API_KEY_V1, TWITTER_API_SECRET_V1, TWITTER_ACCESS_TOKEN_V1, TWITTER_ACCESS_TOKEN_SECRET_V1]):
        logger.error("❌ One or more Twitter API credentials are not fully set. Please check your .env file and Twitter Developer Portal settings. Cannot post to Twitter.")
        return

    try:
        # Initialize tweepy v1.1 API for media upload if not already done
        if twitter_v1_api is None:
            try:
                auth_v1 = tweepy.OAuth1UserHandler(
                    TWITTER_API_KEY_V1,
                    TWITTER_API_SECRET_V1,
                    TWITTER_ACCESS_TOKEN_V1,
                    TWITTER_ACCESS_TOKEN_SECRET_V1
                )
                twitter_v1_api = tweepy.API(auth_v1)
                logger.info("🐦 Initialized Tweepy v1.1 API for media upload.")
            except Exception as e:
                logger.error("❌ Failed to initialize Tweepy v1.1 API: %s", e)
                return # Cannot proceed without v1.1 API for media upload

        media_ids = []
        if image_path and os.path.exists(image_path):
            logger.info("🐦 Uploading image to Twitter media endpoint: %s", image_path)
            try:
                # Upload media using v1.1 API
                media = await asyncio.to_thread(twitter_v1_api.media_upload, filename=image_path)
                media_ids.append(media.media_id_string)
                logger.info("✅ Image uploaded to Twitter media. Media ID: %s", media.media_id_string)
            except Exception as media_upload_e:
                logger.exception("❌ Failed to upload image to Twitter media:")
                # Continue without image if upload fails
                media_ids = []

        async with httpx.AsyncClient() as client:
            logger.info("🐦 Attempting to post to Twitter with caption: '%s' and media_ids: %s", caption, media_ids)
            payload = {"text": caption}
            if media_ids:
                payload["media"] = {"media_ids": media_ids}
            
            # Use the current TWITTER_ACCESS_TOKEN from os.environ
            current_access_token = os.getenv("TWITTER_ACCESS_TOKEN")
            response = await client.post(
                "https://api.twitter.com/2/tweets",
                headers={"Authorization": f"Bearer {current_access_token}"},
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
                    # Retry posting with the new token
                    media_ids = [] # Re-upload media if needed
                    if image_path and os.path.exists(image_path):
                        logger.info("🐦 Retrying image upload to Twitter media endpoint: %s", image_path)
                        media = await asyncio.to_thread(twitter_v1_api.media_upload, filename=image_path)
                        media_ids.append(media.media_id_string)
                        logger.info("✅ Image uploaded to Twitter media on retry. Media ID: %s", media.media_id_string)

                    async with httpx.AsyncClient() as client:
                        logger.info("🐦 Retrying Twitter post with new token...")
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
                except Exception as retry_e:
                    logger.error("Unexpected error during Twitter post retry: %s", retry_e)
            else:
                logger.error("❌ Failed to refresh Twitter token. Please regenerate tokens in Twitter Developer Portal.")
        else:
            logger.error("❌ Twitter post failed: %s - Response: %s", e.response.status_code, e.response.text)
    except Exception as e:
        logger.error("Unexpected error while posting to Twitter: %s", e)

# --- Instagram Posting Functions ---

async def post_to_instagram_feed(image_url: str, caption: str):
    """
    Posts an image with a caption to Instagram Feed via the Graph API.
    Requires IG_ACCOUNT_ID and IG_ACCESS_TOKEN.
    """
    if not all([IG_ACCOUNT_ID, IG_ACCESS_TOKEN]):
        logger.error("❌ Instagram Account ID or Access Token not set. Cannot post to Instagram Feed.")
        return

    try:
        container_url = f"https://graph.facebook.com/v19.0/{IG_ACCOUNT_ID}/media"
        publish_url = f"https://graph.facebook.com/v19.0/{IG_ACCOUNT_ID}/media_publish"

        async with httpx.AsyncClient(timeout=30.0) as client:
            logger.info("📸 Creating IG Feed media container for image: %s", image_url)
            container_response = await client.post(container_url, data={
                "image_url": image_url,
                "caption": caption,
                "access_token": IG_ACCESS_TOKEN
            })
            container_data = container_response.json()
            logger.info("📸 IG Feed Container Response: %s", container_data)

            if 'id' in container_data:
                container_id = container_data['id']
                logger.info("📸 Publishing IG Feed with container ID: %s", container_id)
                publish_response = await client.post(publish_url, data={
                    "creation_id": container_id,
                    "access_token": IG_ACCESS_TOKEN
                })
                publish_data = publish_response.json()
                logger.info("✅ IG Feed Published Response: %s", publish_data)
                if 'id' in publish_data:
                    logger.info("✅ Successfully posted to Instagram Feed! Post ID: %s", publish_data['id'])
                else:
                    logger.error("❌ Instagram Feed publish failed: %s", publish_data)
            else:
                logger.error("❌ Failed to create IG Feed media container. Error: %s", container_data.get('error', 'Unknown error'))

    except httpx.HTTPStatusError as e:
        logger.exception("Instagram Feed HTTP error: %s - Response: %s", e.response.status_code, e.response.text)
    except httpx.RequestError as e:
        logger.exception("Instagram Feed request error: %s", e)
    except Exception as e:
        logger.exception("An unexpected error occurred while posting to Instagram Feed:")

async def post_to_instagram_story(image_url: str):
    """
    Posts an image to Instagram Stories.
    Requires IG_ACCOUNT_ID and IG_ACCESS_TOKEN.
    NOTE: Instagram Stories API does not support a direct 'caption' for visible text.
    Text overlays or stickers require more complex API parameters.
    """
    if not all([IG_ACCOUNT_ID, IG_ACCESS_TOKEN]):
        logger.error("❌ Instagram Account ID or Access Token not set. Cannot post to Instagram Story.")
        return

    try:
        container_url = f"https://graph.facebook.com/v19.0/{IG_ACCOUNT_ID}/media"
        publish_url = f"https://graph.facebook.com/v19.0/{IG_ACCOUNT_ID}/media_publish"

        async with httpx.AsyncClient(timeout=30.0) as client:
            logger.info("📸 Creating IG Story media container for image: %s", image_url)
            story_data = {
                "image_url": image_url,
                "media_type": "STORIES",
                "access_token": IG_ACCESS_TOKEN
            }
            container_response = await client.post(container_url, data=story_data)
            container_data = container_response.json()
            logger.info("📸 IG Story Container: %s", container_data)

            if 'id' in container_data:
                container_id = container_data['id']
                logger.info("📸 Publishing IG Story with container ID: %s", container_id)
                publish_response = await client.post(publish_url, data={
                    "creation_id": container_id,
                    "access_token": IG_ACCESS_TOKEN
                })
                publish_data = publish_response.json()
                logger.info("✅ IG Story Published: %s", publish_data)
                if 'id' in publish_data:
                    logger.info("✅ Successfully posted to Instagram Story! Story ID: %s", publish_data['id'])
                else:
                    logger.error("❌ Instagram Story publish failed: %s", publish_data)
            else:
                logger.error("❌ Failed to create IG Story media container. Error: %s", container_data.get('error', 'Unknown error'))

    except httpx.HTTPStatusError as e:
        logger.exception("Instagram Story HTTP error: %s - Response: %s", e.response.status_code, e.response.text)
    except httpx.RequestError as e:
        logger.exception("Instagram Story request error: %s", e)
    except Exception as e:
        logger.exception("An unexpected error occurred while posting to Instagram Story:")

# --- Facebook Page Posting (Note: often requires App Review for permissions) ---

async def post_to_facebook_page(image_url: str, caption: str):
    """
    Posts an image with a caption to a specified Facebook Page.
    Requires IG_PAGE_ID (which is the Facebook Page ID) and IG_ACCESS_TOKEN.
    NOTE: Direct posting to Facebook Pages requires specific permissions (pages_manage_posts)
    and often App Review, as 'publish_actions' is deprecated. This function will likely fail
    unless your Facebook App is fully configured and approved for these permissions.
    """
    if not all([IG_PAGE_ID, IG_ACCESS_TOKEN]):
        logger.error("❌ Facebook Page ID or Access Token not set. Cannot post to Facebook Page.")
        return

    try:
        page_photos_url = f"https://graph.facebook.com/v19.0/{IG_PAGE_ID}/photos"

        async with httpx.AsyncClient(timeout=30.0) as client:
            logger.info("🌐 Attempting to post to Facebook Page %s...", IG_PAGE_ID)
            response = await client.post(page_photos_url, data={
                "url": image_url, # Use the Cloudinary URL
                "caption": caption,
                "access_token": IG_ACCESS_TOKEN
            })
            response.raise_for_status()
            response_data = response.json()
            logger.info("✅ Facebook Page post response: %s", response_data)
            if 'id' in response_data:
                logger.info("✅ Successfully posted to Facebook Page! Post ID: %s", response_data['id'])
            else:
                logger.error("❌ Facebook Page post failed: %s", response_data)

    except httpx.HTTPStatusError as e:
        logger.exception("Facebook Page HTTP error: %s - Response: %s", e.response.status_code, e.response.text)
        logger.error("Facebook Page posting failed due to permissions. Ensure your Facebook App has 'pages_manage_posts' permission and a valid Page Access Token.")
    except httpx.RequestError as e:
        logger.exception("Facebook Page request error: %s", e)
    except Exception as e:
        logger.exception("An unexpected error occurred while posting to Facebook Page:")

# --- Telegram Channel Posting ---

async def post_to_telegram_channel(image_path: str, caption: str, bot_instance: telegram.Bot):
    """
    Posts an image with a caption to a specified Telegram channel.
    Requires TELEGRAM_CHANNEL_ID.
    """
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

# --- Telegram Bot Message Handler ---

async def handle_telegram_message(update: telegram.Update, bot_instance: telegram.Bot):
    """
    Handles incoming messages from Telegram.
    Downloads photo, uploads to Cloudinary, and posts to various social media.
    """
    image_path = None
    try:
        if not update.message:
            logger.warning("Received update without a message object.")
            return

        message = update.message
        logger.info("Received message from %s: %s", message.chat.username, message.text or "No text (likely a photo)")

        caption = message.caption or message.text or "No caption"

        if message.photo:
            # Download the photo
            file_id = message.photo[-1].file_id
            file_obj = await bot_instance.get_file(file_id)
            image_path = os.path.join(os.getcwd(), f"temp_{file_id}.jpg")
            await file_obj.download_to_drive(image_path)
            logger.info("📥 Photo downloaded to %s", image_path)

            # --- Image dimension check for Instagram Feed ---
            is_feed_compatible = False
            if os.path.exists(image_path):
                try:
                    with Image.open(image_path) as img:
                        width, height = img.size
                        aspect_ratio = width / height

                        # Instagram Feed supports aspect ratios between 4:5 (0.8) and 1.91:1 (1.91)
                        MIN_FEED_ASPECT_RATIO = 0.8
                        MAX_FEED_ASPECT_RATIO = 1.91

                        is_feed_compatible = (aspect_ratio >= MIN_FEED_ASPECT_RATIO and aspect_ratio <= MAX_FEED_ASPECT_RATIO)
                        logger.info("Image dimensions: %dx%d, Aspect Ratio: %.2f. Feed compatible: %s", width, height, aspect_ratio, is_feed_compatible)
                except Exception as e:
                    logger.exception("Error checking image aspect ratio. Assuming not feed compatible.")
                    is_feed_compatible = False

            # Upload to Cloudinary
            cloudinary_image_url = None
            if CLOUDINARY_CLOUD_NAME and os.path.exists(image_path):
                logger.info("☁️ Uploading photo to Cloudinary...")
                try:
                    result = await asyncio.to_thread(cloudinary.uploader.upload, image_path)
                    cloudinary_image_url = result['secure_url']
                    logger.info("☁️ Uploaded to Cloudinary: %s", cloudinary_image_url)
                except Exception as e:
                    logger.exception("❌ Failed to upload image to Cloudinary:")
            else:
                logger.warning("Cloudinary not configured or image file missing, skipping Cloudinary upload.")

            # Prepare tasks for concurrent posting
            posting_tasks = []

            # Add Instagram Feed posting if compatible and Cloudinary URL available
            if is_feed_compatible and cloudinary_image_url:
                posting_tasks.append(post_to_instagram_feed(cloudinary_image_url, caption))
                logger.info("Adding task to post to Instagram Feed.")
            else:
                logger.info("Image aspect ratio is NOT compatible with Instagram Feed OR Cloudinary URL not available. Skipping Instagram Feed post.")

            # Add Instagram Stories posting if Cloudinary URL available
            if cloudinary_image_url:
                posting_tasks.append(post_to_instagram_story(cloudinary_image_url))
                logger.info("Adding task to post to Instagram Stories.")
            else:
                logger.info("Cloudinary URL not available. Skipping Instagram Stories post.")

            # Always add Twitter posting (caption and local image path)
            posting_tasks.append(post_to_twitter(caption, image_path))
            logger.info("Adding task to post to Twitter with image.")

            # Always add Telegram Channel posting (local image path)
            posting_tasks.append(post_to_telegram_channel(image_path, caption, bot_instance))
            logger.info("Adding task to post to Telegram Channel.")

            # Always add Facebook Page posting if Cloudinary URL available
            if cloudinary_image_url:
                posting_tasks.append(post_to_facebook_page(cloudinary_image_url, caption))
                logger.info("Adding task to post to Facebook Page.")
            else:
                logger.info("Cloudinary URL not available. Skipping Facebook Page post.")

            # Execute all prepared posting tasks concurrently
            await asyncio.gather(*posting_tasks)

            await message.reply_text("✅ Photo and caption successfully processed for social media!")

        elif message.text:
            # For text-only messages, only post to Twitter and Telegram Channel
            posting_tasks = []
            posting_tasks.append(post_to_twitter(message.text))
            logger.info("Adding task to post text to Twitter.")
            # For Telegram channel, we need to send a message, not a photo
            if TELEGRAM_CHANNEL_ID:
                try:
                    logger.info("✈️ Posting text to Telegram channel %s...", TELEGRAM_CHANNEL_ID)
                    await bot_instance.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=message.text)
                    logger.info("✅ Successfully posted text to Telegram channel!")
                except Exception as e:
                    logger.exception("❌ Error posting text to Telegram channel:")
            else:
                logger.warning("TELEGRAM_CHANNEL_ID is not set. Skipping text post to Telegram channel.")

            await asyncio.gather(*posting_tasks)
            await message.reply_text("✅ Text message successfully processed for social media!")
        else:
            logger.warning("Unsupported message type received.")
            await message.reply_text("I can only process photo or text messages. Please send a photo or text.")

    except Exception as e:
        logger.exception("Error handling Telegram message:")
        if update.message:
            await update.message.reply_text("❌ Failed to process your request and post the content. Please check logs for details.")
    finally:
        # Clean up the local image file after processing
        if image_path and os.path.exists(image_path):
            os.remove(image_path)
            logger.info("🗑️ Cleaned up temporary file: %s", image_path)

# --- Main Bot Function ---

async def main():
    """
    Initializes and runs the Telegram bot.
    """
    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
    
    # Get bot info to confirm token is valid
    try:
        bot_info = await bot.get_me()
        logger.info("🚀 Telegram Bot is running as @%s.", bot_info.username)
    except telegram.error.InvalidToken:
        logger.error("❌ Invalid Telegram Bot Token. Please check your TELEGRAM_BOT_TOKEN in the .env file.")
        return
    except Exception as e:
        logger.error("❌ Error getting Telegram bot info: %s", e)
        return

    # Delete any existing webhooks to ensure polling works
    try:
        await bot.delete_webhook()
        logger.info("Webhook deleted to ensure polling mode.")
    except Exception as e:
        logger.warning("Could not delete webhook (might not exist): %s", e)

    update_id = 0
    while True:
        try:
            updates = await bot.get_updates(offset=update_id, timeout=10) # Add timeout for robustness
            # logger.info("Received updates: %s", [u.to_dict() for u in updates]) # Uncomment for detailed update logging
            for update in updates:
                if update.update_id >= update_id:
                    update_id = update.update_id + 1
                    await handle_telegram_message(update, bot) # Pass bot instance
            await asyncio.sleep(1) # Poll every second
        except telegram.error.TimedOut:
            # This is normal if no updates for a while, just continue polling
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

