import os
import tweepy
import webbrowser
from dotenv import load_dotenv
import urllib.parse
import time

# Load environment variables
load_dotenv()

# --- Configuration ---
# Get your Client ID and Client Secret from your Twitter Developer App settings
# Ensure your app has "Read and Write" and "Offline Access" permissions enabled.
CLIENT_ID = os.getenv("TWITTER_CLIENT_ID")
CLIENT_SECRET = os.getenv("TWITTER_CLIENT_SECRET") # Only needed if your app is confidential
# This MUST match the Callback URI you configured in your Twitter Developer App
# Use your actual website's HTTPS URL here.
REDIRECT_URI = os.getenv("TWITTER_REDIRECT_URI", "https://9jacashflow.com") # Default to your website

def get_oauth2_tokens():
    if not CLIENT_ID:
        print("Error: TWITTER_CLIENT_ID environment variable not set.")
        print("Please set TWITTER_CLIENT_ID in your .env file.")
        return
    if not REDIRECT_URI:
        print("Error: TWITTER_REDIRECT_URI environment variable not set.")
        print("Please set TWITTER_REDIRECT_URI in your .env file (e.g., https://9jacashflow.com).")
        return

    # Initialize the OAuth2UserHandler
    oauth2_user_handler = tweepy.OAuth2UserHandler(
        client_id=CLIENT_ID,
        redirect_uri=REDIRECT_URI,
        scope=["tweet.read", "tweet.write", "users.read", "offline.access"], # Essential scopes
        client_secret=CLIENT_SECRET # Include if your app is confidential
    )

    # Get the authorization URL
    authorization_url = oauth2_user_handler.get_authorization_url()

    print(f"Please open this URL in your browser to authorize your app:")
    print(authorization_url)
    webbrowser.open(authorization_url)

    # Wait for the user to paste the full redirect URL
    authorization_response = input(
        f"\nAfter authorizing, Twitter will redirect you to {REDIRECT_URI}. "
        "Please copy the *entire* URL from your browser's address bar and paste it here: "
    )

    try:
        # Fetch the access token and refresh token
        tokens = oauth2_user_handler.fetch_token(authorization_response)

        access_token = tokens['access_token']
        refresh_token = tokens.get('refresh_token') # Refresh token is optional but highly recommended

        print("\n--- Successfully obtained Twitter API v2 User Context Tokens ---")
        print(f"TWITTER_ACCESS_TOKEN='{access_token}'")
        if refresh_token:
            print(f"TWITTER_REFRESH_TOKEN='{refresh_token}'")
        else:
            print("Warning: No refresh token obtained. Access token will expire in 2 hours.")
            print("Ensure 'Offline Access' scope is enabled in your Twitter Developer App.")
        print("\nIMPORTANT: Add these lines to your .env file (for your main bot script)!")
        print("------------------------------------------------------------------")

    except Exception as e:
        print(f"\nError fetching tokens: {e}")
        print("Please ensure you pasted the full redirect URL and that your Client ID/Secret are correct.")
        print("Also, double-check your App's Callback URI and permissions in the Twitter Developer Portal.")


if __name__ == "__main__":
    get_oauth2_tokens()
