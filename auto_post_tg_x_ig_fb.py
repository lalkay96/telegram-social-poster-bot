from dotenv import load_dotenv
import os
import tweepy
import requests
from telegram.ext import Application, CommandHandler

load_dotenv()

# Telegram setup
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")

# Twitter setup
twitter_client = tweepy.Client(
    consumer_key=os.getenv("TWITTER_API_KEY"),
    consumer_secret=os.getenv("TWITTER_API_SECRET"),
    access_token=os.getenv("TWITTER_ACCESS_TOKEN"),
    access_token_secret=os.getenv("TWITTER_ACCESS_SECRET")
)

# Instagram/Facebook setup
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
IG_ACCOUNT_ID = os.getenv("IG_ACCOUNT_ID")
FB_PAGE_ID = os.getenv("IG_PAGE_ID")

def post_to_instagram(caption, image_url=None):
    url = f"https://graph.facebook.com/v20.0/{IG_ACCOUNT_ID}/media"
    params = {
        "access_token": IG_ACCESS_TOKEN,
        "caption": caption
    }
    if image_url:
        params["image_url"] = image_url
    response = requests.post(url, params=params)
    if response.status_code == 200:
        media_id = response.json().get("id")
        publish_url = f"https://graph.facebook.com/v20.0/{IG_ACCOUNT_ID}/media_publish"
        publish_response = requests.post(publish_url, params={"creation_id": media_id, "access_token": IG_ACCESS_TOKEN})
        return publish_response.status_code == 200
    return False

def post_to_facebook(caption, image_url=None):
    url = f"https://graph.facebook.com/v20.0/{FB_PAGE_ID}/feed"
    params = {
        "access_token": IG_ACCESS_TOKEN,
        "message": caption
    }
    if image_url:
        params["link"] = image_url  # Use /photos endpoint for images
    response = requests.post(url, params=params)
    return response.status_code == 200

async def post_to_telegram(context, message, photo_url=None):
    try:
        if photo_url:
            await context.bot.send_photo(chat_id=TELEGRAM_CHANNEL_ID, photo=photo_url, caption=message)
        else:
            await context.bot.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=message)
        return True
    except Exception as e:
        return str(e)

async def post_to_all(update, context):
    message = update.message.text.replace("/post ", "")
    image_url = None
    if update.message.photo:
        photo = update.message.photo[-1]  # Get highest resolution
        file = await context.bot.get_file(photo.file_id)
        image_url = file.file_path  # Telegram file URL

    # Post to Telegram channel
    try:
        telegram_result = await post_to_telegram(context, message, image_url)
        telegram_status = "Posted to Telegram channel!" if telegram_result is True else f"Telegram error: {telegram_result}"
    except Exception as e:
        telegram_status = f"Telegram error: {str(e)}"

    # Post to Twitter
    try:
        twitter_client.create_tweet(text=message)
        twitter_status = "Posted to Twitter!"
    except Exception as e:
        twitter_status = f"Twitter error: {str(e)}"

    # Post to Instagram
    try:
        if post_to_instagram(message, image_url):
            ig_status = "Posted to Instagram!"
        else:
            ig_status = "Instagram posting failed."
    except Exception as e:
        ig_status = f"Instagram error: {str(e)}"

    # Post to Facebook
    try:
        if post_to_facebook(message, image_url):
            fb_status = "Posted to Facebook!"
        else:
            fb_status = "Facebook posting failed."
    except Exception as e:
        fb_status = f"Facebook error: {str(e)}"

    # Reply to user
    await update.message.reply_text(f"{telegram_status}\n{twitter_status}\n{ig_status}\n{fb_status}")

def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("post", post_to_all))
    app.run_polling()

if __name__ == "__main__":
    main()