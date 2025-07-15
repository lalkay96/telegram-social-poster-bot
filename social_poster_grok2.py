import signal
import sys
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
# Twitter v1.1 for media uploads
twitter_api_v1 = tweepy.API(
    tweepy.OAuth1UserHandler(
        os.getenv("TWITTER_API_KEY"),
        os.getenv("TWITTER_API_SECRET"),
        os.getenv("TWITTER_ACCESS_TOKEN"),
        os.getenv("TWITTER_ACCESS_SECRET")
    )
)

# Instagram/Facebook setup
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
IG_ACCOUNT_ID = os.getenv("IG_ACCOUNT_ID")
FB_PAGE_ID = os.getenv("IG_PAGE_ID")

def post_to_instagram(caption, media_url=None, is_video=False):
    url = f"https://graph.facebook.com/v20.0/{IG_ACCOUNT_ID}/media"
    params = {"access_token": IG_ACCESS_TOKEN, "caption": caption}
    if media_url:
        params["media_type"] = "VIDEO" if is_video else "IMAGE"
        params["image_url" if not is_video else "video_url"] = media_url
        if is_video:
            params["media_type"] = "REELS"  # Optional: for Instagram Reels
    try:
        response = requests.post(url, params=params)
        if response.status_code == 200:
            media_id = response.json().get("id")
            publish_url = f"https://graph.facebook.com/v20.0/{IG_ACCOUNT_ID}/media_publish"
            publish_response = requests.post(publish_url, params={"creation_id": media_id, "access_token": IG_ACCESS_TOKEN})
            return publish_response.status_code == 200, response.json()
        return False, response.json()
    except Exception as e:
        return False, {"error": {"message": str(e)}}

def post_to_facebook(caption, media_url=None, is_video=False):
    url = f"https://graph.facebook.com/v20.0/{FB_PAGE_ID}/{'videos' if is_video else 'photos'}"
    params = {"access_token": IG_ACCESS_TOKEN}
    if is_video:
        params["file_url"] = media_url
        params["description"] = caption
    else:
        params["url"] = media_url
        params["caption"] = caption
    try:
        response = requests.post(url, params=params)
        return response.status_code == 200, response.json()
    except Exception as e:
        return False, {"error": {"message": str(e)}}

async def post_to_telegram(context, message, photo_url=None, video_url=None):
    try:
        if video_url:
            await context.bot.send_video(chat_id=TELEGRAM_CHANNEL_ID, video=video_url, caption=message)
        elif photo_url:
            await context.bot.send_photo(chat_id=TELEGRAM_CHANNEL_ID, photo=photo_url, caption=message)
        else:
            await context.bot.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=message)
        return True, None
    except Exception as e:
        return False, str(e)

async def post_to_all(update, context):
    message = update.message.text.replace("/post ", "") if update.message.text else ""
    photo_url = None
    video_url = None
    is_video = False

    # Check for photo or video
    if update.message.photo:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        photo_url = file.file_path
    elif update.message.video:
        video = update.message.video
        file = await context.bot.get_file(video.file_id)
        video_url = file.file_path
        is_video = True

    # Post to Telegram channel
    telegram_success, telegram_error = await post_to_telegram(context, message, photo_url, video_url)
    telegram_status = "Posted to Telegram channel!" if telegram_success else f"Telegram error: {telegram_error}"

    # Post to Twitter
    try:
        if photo_url or video_url:
            media = twitter_api_v1.media_upload(filename="media" + (".mp4" if is_video else ".jpg"), file=requests.get(photo_url or video_url).content)
            twitter_client.create_tweet(text=message, media_ids=[media.media_id])
        else:
            twitter_client.create_tweet(text=message)
        twitter_status = "Posted to Twitter!"
    except Exception as e:
        twitter_status = f"Twitter error: {str(e)}"

    # Post to Instagram
    ig_success, ig_response = post_to_instagram(message, photo_url or video_url, is_video)
    ig_status = "Posted to Instagram!" if ig_success else f"Instagram error: {ig_response.get('error', {}).get('message', 'Unknown error')}"

    # Post to Facebook
    fb_success, fb_response = post_to_facebook(message, photo_url or video_url, is_video)
    fb_status = "Posted to Facebook!" if fb_success else f"Facebook error: {fb_response.get('error', {}).get('message', 'Unknown error')}"

    # Reply to user
    await update.message.reply_text(f"{telegram_status}\n{twitter_status}\n{ig_status}\n{fb_status}")

def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("post", post_to_all))

    def handle_shutdown(signum, frame):
        print("Shutting down bot...")
        app.updater.stop()
        app.stop_running()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    app.run_polling()

if __name__ == "__main__":
    main()