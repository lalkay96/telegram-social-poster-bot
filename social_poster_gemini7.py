import os
import logging
import cloudinary
import cloudinary.uploader
import httpx
import asyncio
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from PIL import Image # Import Pillow for image dimension check
import os # Import os for file cleanup

# Import tweepy for Twitter API v2 interaction
import tweepy

# Load environment variables from .env file
load_dotenv()

# --- Configuration from Environment Variables ---
# Telegram Bot Token
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID") # New: Telegram Channel ID

# Instagram API credentials
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
IG_PAGE_ID = os.getenv("IG_PAGE_ID") # Facebook Page ID for posting to Facebook Page
IG_ACCOUNT_ID = os.getenv("IG_ACCOUNT_ID") # Instagram Business Account ID

# Twitter API v2 OAuth 2.0 User Context credentials for posting
TWITTER_CLIENT_ID = os.getenv("TWITTER_CLIENT_ID")
TWITTER_CLIENT_SECRET = os.getenv("TWITTER_CLIENT_SECRET") # Only needed if your app is confidential
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_REFRESH_TOKEN = os.getenv("TWITTER_REFRESH_TOKEN")

# Cloudinary configuration
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global variables to store tweepy clients and manage token refreshing
twitter_v2_client = None # For Twitter API v2 operations (e.g., create_tweet)
twitter_v1_api = None    # For Twitter API v1.1 operations (e.g., media_upload)

# --- Social Media Posting Functions ---

async def post_to_instagram(image_url: str, caption: str):
    """
    Posts an image with a caption to Instagram Feed via the Graph API.
    Requires IG_ACCOUNT_ID and IG_ACCESS_TOKEN.
    """
    try:
        # Endpoint to create a media container for feed
        container_url = f"https://graph.facebook.com/v19.0/{IG_ACCOUNT_ID}/media"
        # Endpoint to publish the media container
        publish_url = f"https://graph.facebook.com/v19.0/{IG_ACCOUNT_ID}/media_publish"

        # Set a timeout for HTTP requests (e.g., 30 seconds)
        async with httpx.AsyncClient(timeout=30.0) as client:
            logger.info("📸 Creating IG Feed media container for image: %s", image_url)
            # Send request to create media container
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
                # Send request to publish the media
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
    """
    try:
        # Endpoint to create a media container for stories
        container_url = f"https://graph.facebook.com/v19.0/{IG_ACCOUNT_ID}/media"
        publish_url = f"https://graph.facebook.com/v19.0/{IG_ACCOUNT_ID}/media_publish"

        async with httpx.AsyncClient(timeout=30.0) as client:
            logger.info("📸 Creating IG Story media container for image: %s", image_url)
            container_response = await client.post(container_url, data={
                "image_url": image_url,
                "media_type": "STORIES", # This is the key difference for stories
                "access_token": IG_ACCESS_TOKEN
            })
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


async def post_to_twitter(caption: str, image_path: str = None):
    """
    Posts a tweet with the given caption and optionally an image using tweepy.
    Handles token refreshing automatically.
    """
    global twitter_v2_client, twitter_v1_api

    # Log the loaded environment variables for debugging
    logger.info("Twitter Env Vars Loaded: CLIENT_ID=%s, CLIENT_SECRET=%s, ACCESS_TOKEN=%s, REFRESH_TOKEN=%s",
                TWITTER_CLIENT_ID,
                "*" * len(TWITTER_CLIENT_SECRET) if TWITTER_CLIENT_SECRET else "None", # Mask secret
                "*" * len(TWITTER_ACCESS_TOKEN) if TWITTER_ACCESS_TOKEN else "None", # Mask token
                "*" * len(TWITTER_REFRESH_TOKEN) if TWITTER_REFRESH_TOKEN else "None") # Mask token


    # Ensure all required Twitter credentials are set
    if not all([TWITTER_CLIENT_ID, TWITTER_CLIENT_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_REFRESH_TOKEN]):
        logger.error("❌ Twitter API v2 OAuth 2.0 User Context credentials (Client ID, Client Secret, Access Token, Refresh Token) are not fully set. Please run the token generation script first and update your .env file. Cannot post to Twitter.")
        return

    try:
        # Initialize tweepy clients if not already done
        if twitter_v2_client is None or twitter_v1_api is None:
            # Initialize v2 Client for tweet posting
            # For OAuth 2.0 User Context, the Client needs consumer_key/secret for the internal OAuth1UserHandler
            # used for certain operations (like media upload via v1.1 API) or when user_auth=True is set.
            twitter_v2_client = tweepy.Client(
                bearer_token=TWITTER_ACCESS_TOKEN, # OAuth 2.0 Access Token
                consumer_key=TWITTER_CLIENT_ID,
                consumer_secret=TWITTER_CLIENT_SECRET,
                access_token=TWITTER_ACCESS_TOKEN, # Used by tweepy's internal OAuth1UserHandler
                access_token_secret=TWITTER_REFRESH_TOKEN # Used by tweepy's internal OAuth1UserHandler (refresh token)
            )
            logger.info("🐦 Initialized Tweepy v2 Client.")

            # Initialize v1.1 API for media upload using OAuth1UserHandler for compatibility
            # Pass OAuth 2.0 tokens into OAuth 1.0a handler for v1.1 API
            auth_v1 = tweepy.OAuth1UserHandler(
                TWITTER_CLIENT_ID,
                TWITTER_CLIENT_SECRET,
                TWITTER_ACCESS_TOKEN, # This is the OAuth 2.0 Access Token
                TWITTER_REFRESH_TOKEN # This is the OAuth 2.0 Refresh Token (used as access_token_secret)
            )
            twitter_v1_api = tweepy.API(auth_v1)
            logger.info("🐦 Initialized Tweepy v1.1 API for media upload.")


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

        # Attempt to create the tweet
        logger.info("🐦 Attempting to post to Twitter with caption: '%s' and media_ids: %s", caption, media_ids)
        # Explicitly set user_auth=True to ensure it uses the user context
        response = await asyncio.to_thread(twitter_v2_client.create_tweet, text=caption, media_ids=media_ids if media_ids else None, user_auth=True)

        # Check for successful tweet creation
        if response.data and 'id' in response.data:
            logger.info("✅ Successfully posted to Twitter! Tweet ID: %s", response.data['id'])
        else:
            logger.error("❌ Twitter post failed: %s", response.errors)

    except tweepy.TwitterServerError as e:
        # Handle token expiration (401 Unauthorized) or other server errors
        if e.response and e.response.status_code == 401 and "Unauthorized" in str(e.response.text):
            logger.info("🔄 Twitter Access Token unauthorized/expired. Attempting to refresh token...")
            try:
                # Refresh the token using tweepy's built-in refresh mechanism
                new_tokens = await asyncio.to_thread(
                    twitter_v2_client.refresh_token, # Use the v2 client's refresh_token method
                    client_id=TWITTER_CLIENT_ID,
                    client_secret=TWITTER_CLIENT_SECRET, # Pass client_secret for refresh
                    refresh_token=TWITTER_REFRESH_TOKEN # Explicitly pass refresh token
                )
                # Update the global clients with new tokens
                twitter_v2_client = tweepy.Client(
                    bearer_token=new_tokens['access_token'],
                    consumer_key=TWITTER_CLIENT_ID,
                    consumer_secret=TWITTER_CLIENT_SECRET,
                    access_token=new_tokens['access_token'],
                    access_token_secret=new_tokens['refresh_token'] # Update with new refresh token
                )
                # Also re-initialize v1.1 API with the new tokens
                auth_v1 = tweepy.OAuth1UserHandler(
                    TWITTER_CLIENT_ID,
                    TWITTER_CLIENT_SECRET,
                    new_tokens['access_token'],
                    new_tokens['refresh_token']
                )
                twitter_v1_api = tweepy.API(auth_v1)

                # IMPORTANT: Log new tokens for manual .env update.
                logger.warning("🔑 Twitter tokens refreshed! PLEASE UPDATE YOUR .ENV FILE:")
                logger.warning("TWITTER_ACCESS_TOKEN=%s", new_tokens['access_token'])
                logger.warning("TWITTER_REFRESH_TOKEN=%s", new_tokens['refresh_token'])

                # Update the environment variables in memory as well for immediate use
                os.environ["TWITTER_ACCESS_TOKEN"] = new_tokens['access_token']
                os.environ["TWITTER_REFRESH_TOKEN"] = new_tokens['refresh_token']


                # Retry posting the tweet with the new token
                logger.info("🐦 Retrying Twitter post with new token...")
                # Re-attempt media upload if it was intended
                retry_media_ids = []
                if image_path and os.path.exists(image_path):
                    try:
                        media = await asyncio.to_thread(twitter_v1_api.media_upload, filename=image_path)
                        retry_media_ids.append(media.media_id_string)
                        logger.info("✅ Image uploaded to Twitter media on retry. Media ID: %s", media.media_id_string)
                    except Exception as retry_media_upload_e:
                        logger.exception("❌ Failed to upload image to Twitter media on retry:")

                response = await asyncio.to_thread(twitter_v2_client.create_tweet, text=caption, media_ids=retry_media_ids if retry_media_ids else None, user_auth=True)
                if response.data and 'id' in response.data:
                    logger.info("✅ Successfully posted to Twitter after token refresh! Tweet ID: %s", response.data['id'])
                else:
                    logger.error("❌ Twitter post failed even after token refresh: %s", response.errors)

            except Exception as refresh_e:
                logger.exception("❌ Failed to refresh Twitter token or post after refresh:")
                logger.error("Please re-run the token generation script to get new tokens.")
        else:
            logger.exception("Twitter API server error: %s", e)
    except tweepy.TweepyException as e:
        logger.exception("Tweepy error while posting to Twitter:")
    except Exception as e:
        logger.exception("An unexpected error occurred while posting to Twitter:")

async def post_to_telegram_channel(image_path: str, caption: str, context: ContextTypes.DEFAULT_TYPE):
    """
    Posts an image with a caption to a specified Telegram channel.
    Requires TELEGRAM_CHANNEL_ID.
    """
    if not TELEGRAM_CHANNEL_ID:
        logger.error("❌ TELEGRAM_CHANNEL_ID is not set. Cannot post to Telegram channel.")
        return

    try:
        logger.info("✈️ Posting to Telegram channel %s...", TELEGRAM_CHANNEL_ID)
        # Telegram Bot API supports sending local files directly
        with open(image_path, 'rb') as photo_file:
            await context.bot.send_photo(chat_id=TELEGRAM_CHANNEL_ID, photo=photo_file, caption=caption)
        logger.info("✅ Successfully posted to Telegram channel!")
    except Exception as e:
        logger.exception("❌ Error posting to Telegram channel:")

async def post_to_facebook_page(image_url: str, caption: str):
    """
    Posts an image with a caption to a specified Facebook Page.
    Requires IG_PAGE_ID (which is the Facebook Page ID) and IG_ACCESS_TOKEN.
    """
    if not all([IG_PAGE_ID, IG_ACCESS_TOKEN]):
        logger.error("❌ Facebook Page ID or Access Token not set. Cannot post to Facebook Page.")
        return

    try:
        # Facebook Graph API endpoint for page photos
        page_photos_url = f"https://graph.facebook.com/v19.0/{IG_PAGE_ID}/photos"

        async with httpx.AsyncClient(timeout=30.0) as client:
            logger.info("🌐 Posting to Facebook Page %s...", IG_PAGE_ID)
            response = await client.post(page_photos_url, data={
                "url": image_url, # Use the Cloudinary URL
                "caption": caption,
                "access_token": IG_ACCESS_TOKEN
            })
            response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
            response_data = response.json()
            logger.info("✅ Facebook Page post response: %s", response_data)
            if 'id' in response_data:
                logger.info("✅ Successfully posted to Facebook Page! Post ID: %s", response_data['id'])
            else:
                logger.error("❌ Facebook Page post failed: %s", response_data)

    except httpx.HTTPStatusError as e:
        logger.exception("Facebook Page HTTP error: %s - Response: %s", e.response.status_code, e.response.text)
    except httpx.RequestError as e:
        logger.exception("Facebook Page request error: %s", e)
    except Exception as e:
        logger.exception("An unexpected error occurred while posting to Facebook Page:")


# --- Telegram Bot Handler ---

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles incoming photo messages from Telegram.
    Downloads the photo, uploads to Cloudinary, and then posts to Instagram (conditionally),
    Twitter, Telegram Channel, and Facebook Page.
    """
    image_path = None # Initialize image_path to None
    try:
        # Add robust checks for update.message and update.message.photo
        if not update.message:
            logger.warning("Received update without a message object.")
            return # Exit if no message object

        if not update.message.photo:
            logger.warning("Received message without a photo object. Message ID: %s", update.message.message_id)
            # Try to reply if message object exists, even if no photo
            if update.message:
                await update.message.reply_text("I can only process photo messages. Please send a photo.")
            return # Exit if no photo object

        # Proceed with photo processing
        photo_file = await update.message.photo[-1].get_file()
        # Define a temporary path to save the image
        image_path = f"temp_image_{update.message.message_id}.jpg"
        await photo_file.download_to_drive(image_path)
        logger.info("📥 Photo downloaded to %s", image_path)

        # --- Get image dimensions and check aspect ratio for Instagram Feed ---
        is_feed_compatible = False
        try:
            with Image.open(image_path) as img:
                width, height = img.size
                aspect_ratio = width / height

                # Define common acceptable aspect ratio range for Instagram Feed
                # Instagram Feed supports aspect ratios between 4:5 (0.8) and 1.91:1 (1.91)
                MIN_FEED_ASPECT_RATIO = 0.8
                MAX_FEED_ASPECT_RATIO = 1.91

                is_feed_compatible = (aspect_ratio >= MIN_FEED_ASPECT_RATIO and aspect_ratio <= MAX_FEED_ASPECT_RATIO)
                logger.info("Image dimensions: %dx%d, Aspect Ratio: %.2f. Feed compatible: %s", width, height, aspect_ratio, is_feed_compatible)

        except Exception as e:
            logger.exception("Error checking image aspect ratio. Assuming not feed compatible.")
            is_feed_compatible = False # If error, assume not compatible

        # Upload to Cloudinary
        logger.info("☁️ Uploading photo to Cloudinary...")
        result = cloudinary.uploader.upload(image_path)
        image_url = result['secure_url']
        logger.info("☁️ Uploaded to Cloudinary: %s", image_url)

        # Get caption from the message, default to "No caption" if not present
        caption = update.message.caption or "No caption"

        # Prepare tasks for concurrent posting
        posting_tasks = []

        # Conditionally add Instagram Feed posting
        if is_feed_compatible:
            posting_tasks.append(post_to_instagram(image_url, caption))
            logger.info("Adding task to post to Instagram Feed.")
        else:
            logger.info("Image aspect ratio is NOT compatible with Instagram Feed. Skipping feed post.")

        # Always add Instagram Stories posting
        posting_tasks.append(post_to_instagram_story(image_url))
        logger.info("Adding task to post to Instagram Stories.")

        # Always add Twitter posting (caption and image)
        posting_tasks.append(post_to_twitter(caption, image_path))
        logger.info("Adding task to post to Twitter with image.")

        # Always add Telegram Channel posting
        posting_tasks.append(post_to_telegram_channel(image_path, caption, context))
        logger.info("Adding task to post to Telegram Channel.")

        # Always add Facebook Page posting
        posting_tasks.append(post_to_facebook_page(image_url, caption))
        logger.info("Adding task to post to Facebook Page.")


        # Execute all prepared posting tasks concurrently
        await asyncio.gather(*posting_tasks)

        # Only reply if update.message is not None
        if update.message:
            await update.message.reply_text("✅ Photo and caption successfully processed for social media!")

    except Exception as e:
        logger.exception("Error handling photo message:")
        # Only reply if update.message is not None
        if update.message:
            await update.message.reply_text("❌ Failed to process your request and post the content. Please check logs for details.")
    finally:
        # Clean up the local image file after processing
        if image_path and os.path.exists(image_path):
            os.remove(image_path)
            logger.info("🗑️ Cleaned up temporary file: %s", image_path)

# --- Main Bot Function ---

def main(): # This function remains synchronous as per previous fix
    """
    Initializes and runs the Telegram bot.
    """
    # Create the ApplicationBuilder with your bot token
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Add a message handler for photos
    app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_photo))

    logger.info("🚀 Telegram Bot is running... Waiting for messages.")
    # Start the bot. This method is blocking and handles the event loop.
    app.run_polling() # Directly call run_polling

# --- Entry Point ---

if __name__ == '__main__':
    # This ensures that Application.run_polling() manages the event loop directly.
    try:
        main() # Call the synchronous main function
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    except Exception as e:
        logger.exception("An unhandled error occurred in the main execution:")

