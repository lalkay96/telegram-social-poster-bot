import os
import sys
import requests
import time
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
from requests_oauthlib import OAuth1Session
from PIL import Image
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import cloudinary
import cloudinary.uploader
import cloudinary.api

# Load environment variables from .env file
load_dotenv()

# --- Logging Setup ---
def setup_logging():
    """Configures logging to output to both console and a log file."""
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    log_file = os.path.join(log_dir, "app.log")
    log_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Console handler with UTF-8 encoding
    console_handler = logging.StreamHandler(sys.stdout.buffer.raw)
    console_handler.setFormatter(log_formatter)
    console_handler.setLevel(logging.INFO)

    # File handler with rotation and UTF-8 encoding
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=1048576,  # 1 MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(log_formatter)
    file_handler.setLevel(logging.DEBUG)

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

# --- Token Management ---
class TokenManager:
    """Manages the lifecycle of access and refresh tokens for Twitter (v2)."""

    def __init__(self, token_endpoint, client_id, client_secret, refresh_token):
        self.token_endpoint = token_endpoint
        self.client_id = client_id
        self.client_secret = client_secret
        self._access_token = os.getenv("TWITTER_ACCESS_TOKEN")
        self._refresh_token = refresh_token
        self._access_token_expiry = 0
        if self._access_token:
            # Assume a valid token for now to avoid immediate refresh on startup
            self._access_token_expiry = time.time() + 3600

    @property
    def access_token(self):
        """Returns the current access token, refreshing it if expired."""
        if self._is_expired():
            self.refresh_access_token()
        return self._access_token

    def _is_expired(self):
        """Checks if the access token has expired."""
        # Subtract a small buffer time (e.g., 60 seconds) to refresh before true expiration
        return time.time() >= self._access_token_expiry - 60

    def refresh_access_token(self):
        """Requests a new access token using the refresh token."""
        logging.info("🔄 Twitter access token expired. Attempting to refresh token...")
        payload = {
            'grant_type': 'refresh_token',
            'client_id': self.client_id,
            'refresh_token': self._refresh_token,
        }
        auth = (self.client_id, self.client_secret)
        try:
            response = requests.post(self.token_endpoint, data=payload, auth=auth)
            response.raise_for_status()
            data = response.json()
            
            self._access_token = data.get('access_token')
            self._refresh_token = data.get('refresh_token', self._refresh_token)
            expires_in = data.get('expires_in', 7200)
            self._access_token_expiry = time.time() + expires_in - 60
            
            logging.info("✅ Successfully refreshed access token.")
        except requests.exceptions.RequestException as e:
            logging.error(f"❌ Failed to refresh Twitter token: {response.status_code} - Response: {response.text}")
            raise RuntimeError("Failed to refresh Twitter token. Please regenerate tokens.")

# --- Twitter Posting Functionality ---
def upload_twitter_media_v1(image_path):
    """Uploads an image to Twitter using API v1.1 and returns a media ID."""
    logging.info("🐦 Uploading image to Twitter media endpoint (v1.1)...")
    upload_url = "https://upload.twitter.com/1.1/media/upload.json"
    
    # Get v1.1 credentials from .env
    api_key_v1 = os.getenv("TWITTER_API_KEY_V1")
    api_secret_v1 = os.getenv("TWITTER_API_SECRET_V1")
    access_token_v1 = os.getenv("TWITTER_ACCESS_TOKEN_V1")
    access_token_secret_v1 = os.getenv("TWITTER_ACCESS_TOKEN_SECRET_V1")

    if not all([api_key_v1, api_secret_v1, access_token_v1, access_token_secret_v1]):
        logging.error("❌ Missing Twitter API v1.1 credentials.")
        return None

    try:
        oauth = OAuth1Session(
            api_key_v1,
            client_secret=api_secret_v1,
            resource_owner_key=access_token_v1,
            resource_owner_secret=access_token_secret_v1
        )
        with open(image_path, 'rb') as image_file:
            files = {'media': image_file}
            response = oauth.post(upload_url, files=files)
            response.raise_for_status()
            media_id = response.json().get('media_id_string')
            logging.info(f"✅ Image uploaded to Twitter media. Media ID: {media_id}")
            return media_id
    except Exception as e:
        logging.error(f"❌ Failed to upload image to Twitter (v1.1): {e}")
        return None

def post_to_twitter(image_path, caption, access_token):
    """Posts a tweet with an image using API v2."""
    # First, upload the image using the v1.1 endpoint
    media_id = upload_twitter_media_v1(image_path)
    if not media_id:
        return False

    logging.info("✍️ Posting tweet to API v2...")
    tweet_url = "https://api.twitter.com/2/tweets"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "text": caption,
        "media": {"media_ids": [media_id]}
    }
    
    try:
        response = requests.post(tweet_url, headers=headers, json=payload)
        response.raise_for_status()
        logging.info("✅ Successfully posted to Twitter!")
        return True
    except requests.exceptions.HTTPError as e:
        if response.status_code == 401:
            logging.info("🔄 Twitter Access Token unauthorized. Attempting to refresh token...")
            return False
        logging.error(f"❌ Failed to post to Twitter (v2): {response.status_code} - {response.text}")
        return False
    except Exception as e:
        logging.error(f"❌ An error occurred while posting to Twitter (v2): {e}")
        return False

# --- Main Bot Logic ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a message when the command /start is issued."""
    await update.message.reply_text('Hello! I am a social media poster bot. Send me an image with a caption to post it to all your connected accounts.')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles incoming messages, downloads images, and posts to social media."""
    if update.message.photo:
        photo_file_id = update.message.photo[-1].file_id
        photo_caption = update.message.caption if update.message.caption else ""
        
        bot = update.get_bot()
        photo_file = await bot.get_file(photo_file_id)
        
        temp_photo_path = os.path.join("temp", f"{photo_file.file_unique_id}.jpg")
        if not os.path.exists("temp"):
            os.makedirs("temp")

        await photo_file.download_to_drive(temp_photo_path)
        logging.info(f"📥 Photo downloaded to {temp_photo_path}")

        try:
            # Post to social media
            await post_to_all_platforms(temp_photo_path, photo_caption)
            await update.message.reply_text("✅ Successfully posted to all social media platforms!")
        except Exception as e:
            logging.error(f"❌ An error occurred during posting: {e}")
            await update.message.reply_text(f"❌ Failed to post. Please check the logs for details.")
        finally:
            if os.path.exists(temp_photo_path):
                os.remove(temp_photo_path)
                logging.info(f"🗑️ Cleaned up temporary file: {temp_photo_path}")
    else:
        await update.message.reply_text("Please send an image to post.")

async def post_to_all_platforms(image_path, caption):
    """Coordinates posting to all social media platforms."""
    # --- Twitter ---
    if os.getenv("TWITTER_CLIENT_ID"):
        logging.info("🐦 Posting to Twitter...")
        twitter_posted = False
        retry_count = 0
        while not twitter_posted and retry_count < 2:
            try:
                # Use the access token property, which handles the refresh
                access_token = twitter_token_manager.access_token
                twitter_posted = post_to_twitter(image_path, caption, access_token)
            except RuntimeError as e:
                logging.error(f"Twitter posting failed due to token error: {e}")
                break
            retry_count += 1
    
    # --- Instagram ---
    # Placeholder for Instagram logic
    # ...

# --- Main Execution ---
def main() -> None:
    """Start the bot."""
    setup_logging()

    # Get credentials from .env
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    TWITTER_CLIENT_ID = os.getenv("TWITTER_CLIENT_ID")
    TWITTER_CLIENT_SECRET = os.getenv("TWITTER_CLIENT_SECRET")
    TWITTER_REFRESH_TOKEN = os.getenv("TWITTER_REFRESH_TOKEN")
    TWITTER_TOKEN_ENDPOINT = "https://api.twitter.com/2/oauth2/token"

    if not TELEGRAM_BOT_TOKEN:
        logging.error("TELEGRAM_BOT_TOKEN is not set. Please add it to your .env file.")
        return
    
    if TWITTER_CLIENT_ID:
        global twitter_token_manager
        try:
            twitter_token_manager = TokenManager(
                token_endpoint=TWITTER_TOKEN_ENDPOINT,
                client_id=TWITTER_CLIENT_ID,
                client_secret=TWITTER_CLIENT_SECRET,
                refresh_token=TWITTER_REFRESH_TOKEN
            )
        except Exception as e:
            logging.error(f"Failed to initialize Twitter token manager: {e}")
            return

    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Add handlers for commands and messages
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_message))

    # Run the bot until the user presses Ctrl-C
    logging.info("Bot started successfully! Press Ctrl+C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()