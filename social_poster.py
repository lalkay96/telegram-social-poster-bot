import os
import requests
import tweepy
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
from dotenv import load_dotenv

load_dotenv()

# Twitter Setup
auth = tweepy.OAuth1UserHandler(
    os.getenv("TWITTER_API_KEY"),
    os.getenv("TWITTER_API_SECRET"),
    os.getenv("TWITTER_ACCESS_TOKEN"),
    os.getenv("TWITTER_ACCESS_SECRET")
)
twitter_api = tweepy.API(auth)

# Instagram Setup
IG_TOKEN = os.getenv("IG_ACCESS_TOKEN")
IG_PAGE_ID = os.getenv("IG_PAGE_ID")
IG_ACCOUNT_ID = os.getenv("IG_ACCOUNT_ID")

# --- Function to post to Twitter ---
def post_to_twitter(image_path, caption):
    twitter_api.update_status_with_media(status=caption, filename=image_path)

# --- Function to post to Instagram ---
def post_to_instagram(image_path, caption):
    # Step 1: Upload image
    upload_url = f"https://graph.facebook.com/v19.0/{IG_ACCOUNT_ID}/media"
    files = {'image': open(image_path, 'rb')}
    params = {
        'caption': caption,
        'access_token': IG_TOKEN,
        'image_url': '',  # Not used when uploading image file directly
    }
    r1 = requests.post(upload_url, params=params, files=files).json()
    creation_id = r1.get("id")
    if not creation_id:
        print("Error:", r1)
        return

    # Step 2: Publish
    publish_url = f"https://graph.facebook.com/v19.0/{IG_ACCOUNT_ID}/media_publish"
    pub_params = {
        'creation_id': creation_id,
        'access_token': IG_TOKEN
    }
    r2 = requests.post(publish_url, params=pub_params).json()
    print("Instagram response:", r2)

# --- Telegram Handler ---
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.caption:
        caption = update.message.caption
    else:
        caption = "Posted via 9jaCashFlow TG Social Poster Bot 💡"

    photo = await update.message.photo[-1].get_file()
    image_path = f"temp.jpg"
    await photo.download_to_drive(image_path)

    # Post to both platforms
    post_to_twitter(image_path, caption)
    post_to_instagram(image_path, caption)

    await update.message.reply_text("✅ Posted to Twitter & Instagram!")

# --- Main App ---
app = ApplicationBuilder().token("7613226792:AAFYFA_sCybiYbOao6iCr-yYJz72JFncqEA").build()
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

print("Bot running...")
app.run_polling()
