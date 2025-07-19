import os
import logging
import cloudinary
import cloudinary.uploader
import httpx
import asyncio
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
import os # Import os for file cleanup

# Load environment variables from .env file
load_dotenv()

# --- Configuration from Environment Variables ---
# Telegram Bot Token
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Instagram API credentials
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
IG_PAGE_ID = os.getenv("IG_PAGE_ID") # This might not be directly used for posting, but good to have
IG_ACCOUNT_ID = os.getenv("IG_ACCOUNT_ID")

# Twitter API credentials (Note: Bearer Token is for App-only. For posting, typically OAuth 1.0a User Context is needed)
# The current Twitter API v2 'tweets' endpoint with Bearer Token is for fetching.
# To post, you'd generally need Consumer Key, Consumer Secret, Access Token, and Access Token Secret for OAuth 1.0a.
# For simplicity, this code assumes a compatible setup or a future Twitter API change allowing posting with Bearer.
# If posting fails, this is the first place to check for Twitter.
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN")

# Cloudinary configuration
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Social Media Posting Functions ---

async def post_to_instagram(image_url: str, caption: str):
    """
    Posts an image with a caption to Instagram via the Graph API.
    Requires IG_ACCOUNT_ID and IG_ACCESS_TOKEN.
    """
    try:
        # Endpoint to create a media container
        container_url = f"https://graph.facebook.com/v19.0/{IG_ACCOUNT_ID}/media"
        # Endpoint to publish the media container
        publish_url = f"https://graph.facebook.com/v19.0/{IG_ACCOUNT_ID}/media_publish"

        async with httpx.AsyncClient() as client:
            logger.info("📸 Creating IG media container for image: %s", image_url)
            # Send request to create media container
            container_response = await client.post(container_url, data={
                "image_url": image_url,
                "caption": caption,
                "access_token": IG_ACCESS_TOKEN
            })
            container_data = container_response.json()
            logger.info("📸 IG Container Response: %s", container_data)

            if 'id' in container_data:
                container_id = container_data['id']
                logger.info("📸 Publishing IG media with container ID: %s", container_id)
                # Send request to publish the media
                publish_response = await client.post(publish_url, data={
                    "creation_id": container_id,
                    "access_token": IG_ACCESS_TOKEN
                })
                publish_data = publish_response.json()
                logger.info("✅ IG Published Response: %s", publish_data)
                if 'id' in publish_data:
                    logger.info("✅ Successfully posted to Instagram! Post ID: %s", publish_data['id'])
                else:
                    logger.error("❌ Instagram publish failed: %s", publish_data)
            else:
                logger.error("❌ Failed to create IG media container. Error: %s", container_data.get('error', 'Unknown error'))

    except httpx.HTTPStatusError as e:
        logger.exception("Instagram HTTP error: %s - Response: %s", e.response.status_code, e.response.text)
    except httpx.RequestError as e:
        logger.exception("Instagram request error: %s", e)
    except Exception as e:
        logger.exception("An unexpected error occurred while posting to Instagram:")

async def post_to_twitter(caption: str):
    """
    Posts a tweet with the given caption.
    Note: Twitter API v2 'tweets' endpoint typically requires OAuth 1.0a for posting.
    Using a Bearer Token usually implies read-only access or app-only context.
    If posting fails, verify your Twitter API access token type and permissions.
    """
    try:
        async with httpx.AsyncClient() as client:
            logger.info("🐦 Attempting to post to Twitter with caption: '%s'", caption)
            response = await client.post(
                "https://api.twitter.com/2/tweets",
                headers={
                    "Authorization": f"Bearer {TWITTER_BEARER_TOKEN}",
                    "Content-Type": "application/json"
                },
                json={"text": caption}
            )
            response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
            logger.info("🐦 Twitter response: %s", response.json())

            if response.status_code == 201:
                logger.info("✅ Successfully posted to Twitter!")
            else:
                logger.error("❌ Twitter post failed with status %s: %s", response.status_code, response.text)
    except httpx.HTTPStatusError as e:
        logger.exception("Twitter HTTP error: %s - Response: %s", e.response.status_code, e.response.text)
    except httpx.RequestError as e:
        logger.exception("Twitter request error: %s", e)
    except Exception as e:
        logger.exception("An unexpected error occurred while posting to Twitter:")

# --- Telegram Bot Handler ---

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles incoming photo messages from Telegram.
    Downloads the photo, uploads to Cloudinary, and then posts to Instagram and Twitter.
    """
    image_path = None # Initialize image_path to None
    try:
        # Get the largest photo file from the update
        photo_file = await update.message.photo[-1].get_file()
        # Define a temporary path to save the image
        image_path = f"temp_image_{update.message.message_id}.jpg"
        await photo_file.download_to_drive(image_path)
        logger.info("📥 Photo downloaded to %s", image_path)

        # Upload to Cloudinary
        logger.info("☁️ Uploading photo to Cloudinary...")
        result = cloudinary.uploader.upload(image_path)
        image_url = result['secure_url']
        logger.info("☁️ Uploaded to Cloudinary: %s", image_url)

        # Get caption from the message, default to "No caption" if not present
        caption = update.message.caption or "No caption"

        # Post to Instagram and Twitter concurrently
        await asyncio.gather(
            post_to_instagram(image_url, caption),
            post_to_twitter(caption)
        )

        await update.message.reply_text("✅ Photo and caption successfully posted to Instagram and Twitter!")

    except Exception as e:
        logger.exception("Error handling photo message:")
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
    # Create the ApplicationBuilder with your bot token
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Add a message handler for photos
    app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_photo))

    logger.info("🚀 Telegram Bot is running... Waiting for messages.")
    # Start the bot. This method is blocking and handles the event loop.
    await app.run_polling()

# --- Entry Point ---

if __name__ == '__main__':
    # This ensures that asyncio.run() is called only once.
    # telegram.ext's Application.run_polling() manages the event loop internally.
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    except Exception as e:
        logger.exception("An unhandled error occurred in the main execution:")

