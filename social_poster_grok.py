from dotenv import load_dotenv
import os
import tweepy
from telegram.ext import Application, CommandHandler

load_dotenv()
# Twitter API setup
twitter_client = tweepy.Client(
    consumer_key=os.getenv("TWITTER_API_KEY"),
    consumer_secret=os.getenv("TWITTER_API_SECRET"),
    access_token=os.getenv("TWITTER_ACCESS_TOKEN"),
    access_token_secret=os.getenv("TWITTER_ACCESS_SECRET")
)

# Telegram bot setup
async def post_to_twitter(update, context):
    message = update.message.text.replace("/post ", "")
    twitter_client.create_tweet(text=message)
    await update.message.reply_text("Posted to Twitter!")

def main():
    app = Application.builder().token(os.getenv("TELEGRAM_BOT_TOKEN")).build()
    app.add_handler(CommandHandler("post", post_to_twitter))
    app.run_polling()

if __name__ == "__main__":
    main()