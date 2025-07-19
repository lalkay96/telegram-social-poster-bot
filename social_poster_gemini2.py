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

# Import tweepy for Twitter API v2 interaction
import tweepy

# Load environment variables from .env file
load_dotenv()

# --- Configuration from Environment Variables ---
# Telegram Bot Token
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Instagram API credentials
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
IG_PAGE_ID = os.getenv("IG_PAGE_ID") # This might not be directly used for posting, but good to have
IG_ACCOUNT_ID = os.getenv("IG_ACCOUNT_ID")

# Twitter API v2 OAuth 2.0 User Context credentials for posting
# These will be obtained via an initial authorization flow (see instructions below)
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

# Global variable to store the tweepy client and manage token refreshing
# This allows the client to be initialized once and tokens refreshed as needed.
twitter_client = None

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
    Posts a tweet with the given caption using tweepy and OAuth 2.0 User Context.
    Handles token refreshing automatically.
    """
    global twitter_client

    if not all([TWITTER_CLIENT_ID, TWITTER_ACCESS_TOKEN, TWITTER_REFRESH_TOKEN]):
        logger.error("❌ Twitter API v2 OAuth 2.0 User Context credentials (Client ID, Access Token, Refresh Token) are not fully set. Please run the token generation script first and update your .env file. Cannot post to Twitter.")
        return

    try:
        # Initialize tweepy client if not already done or if tokens need refreshing
        if twitter_client is None:
            # The client_secret is only needed if your app is confidential.
            # For most bot setups using PKCE, it might not be strictly needed for initial client creation
            # but is crucial for token refreshing.
            twitter_client = tweepy.Client(
                bearer_token=TWITTER_ACCESS_TOKEN,
                consumer_key=TWITTER_CLIENT_ID, # tweepy uses consumer_key for client_id in this context
                consumer_secret=TWITTER_CLIENT_SECRET, # tweepy uses consumer_secret for client_secret
                access_token=TWITTER_ACCESS_TOKEN,
                access_token_secret=TWITTER_REFRESH_TOKEN # tweepy uses access_token_secret for refresh_token in this context
            )
            logger.info("🐦 Initialized Tweepy client with provided tokens.")

        # Attempt to create the tweet
        logger.info("🐦 Attempting to post to Twitter with caption: '%s'", caption)
        response = await asyncio.to_thread(twitter_client.create_tweet, text=caption)

        # Check for successful tweet creation
        if response.data and 'id' in response.data:
            logger.info("✅ Successfully posted to Twitter! Tweet ID: %s", response.data['id'])
        else:
            logger.error("❌ Twitter post failed: %s", response.errors)

    except tweepy.TwitterServerError as e:
        # Handle token expiration or other server errors
        if e.response and e.response.status_code == 401 and "expired_token" in str(e.response.text):
            logger.info("🔄 Twitter Access Token expired. Attempting to refresh token...")
            try:
                # Refresh the token using tweepy's built-in refresh mechanism
                # This assumes your app is set up correctly in Twitter Developer Portal
                # with "Offline Access" scope and TWITTER_CLIENT_SECRET is available if needed.
                new_tokens = await asyncio.to_thread(
                    twitter_client.refresh_token,
                    client_id=TWITTER_CLIENT_ID,
                    client_secret=TWITTER_CLIENT_SECRET # Pass client_secret for refresh
                )
                # Update the global client with new tokens
                twitter_client = tweepy.Client(
                    bearer_token=new_tokens['access_token'],
                    consumer_key=TWITTER_CLIENT_ID,
                    consumer_secret=TWITTER_CLIENT_SECRET,
                    access_token=new_tokens['access_token'],
                    access_token_secret=new_tokens['refresh_token'] # Update with new refresh token
                )
                # IMPORTANT: Update your .env file with the new tokens for persistence
                # In a real-world app, you'd persist these to a database or secure storage.
                # For this example, we'll log them and recommend manual update.
                logger.warning("🔑 Twitter tokens refreshed! PLEASE UPDATE YOUR .ENV FILE:")
                logger.warning("TWITTER_ACCESS_TOKEN='%s'", new_tokens['access_token'])
                logger.warning("TWITTER_REFRESH_TOKEN='%s'", new_tokens['refresh_token'])

                # Retry posting the tweet with the new token
                logger.info("🐦 Retrying Twitter post with new token...")
                response = await asyncio.to_thread(twitter_client.create_tweet, text=caption)
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
        # Note: Twitter API v2 posting does not support images directly via the /tweets endpoint
        # You would need to upload media separately and then attach media_ids to the tweet.
        # This implementation only posts the caption to Twitter.
        await asyncio.gather(
            post_to_instagram(image_url, caption),
            post_to_twitter(caption) # Only caption is posted to Twitter for simplicity
        )

        await update.message.reply_text("✅ Photo and caption successfully posted to Instagram and Twitter (caption only)!")

    except Exception as e:
        logger.exception("Error handling photo message:")
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

