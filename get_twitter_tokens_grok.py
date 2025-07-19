import requests
import base64
import hashlib
import secrets
import webbrowser
import urllib.parse
import os
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("TWITTER_CLIENT_ID")
CLIENT_SECRET = os.getenv("TWITTER_CLIENT_SECRET")
REDIRECT_URI = "https://9jacashflow.com"
SCOPES = ["tweet.read", "tweet.write", "offline.access"]

def generate_code_verifier():
    return secrets.token_urlsafe(64)[:128]

def generate_code_challenge(verifier):
    challenge = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(challenge).decode().rstrip("=")

def get_authorization_code():
    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)
    state = secrets.token_urlsafe(16)

    auth_url = (
        "https://twitter.com/i/oauth2/authorize?"
        f"response_type=code&client_id={CLIENT_ID}&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
        f"&scope={urllib.parse.quote(' '.join(SCOPES))}&state={state}"
        f"&code_challenge={code_challenge}&code_challenge_method=S256"
    )

    print("Opening browser to authorize app...")
    webbrowser.open(auth_url)
    print("After authorizing, you'll be redirected to a URL.")
    print("Copy the full URL and extract the 'code' parameter (everything between 'code=' and '&').")
    auth_code = input("Paste the authorization code here: ")
    return auth_code, code_verifier, state

def exchange_code_for_tokens(auth_code, code_verifier):
    token_url = "https://api.twitter.com/2/oauth2/token"
    auth_header = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {auth_header}",
    }
    data = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "code_verifier": code_verifier,
    }

    response = requests.post(token_url, headers=headers, data=data)
    response.raise_for_status()
    return response.json()

def main():
    if not all([CLIENT_ID, CLIENT_SECRET]):
        print("Error: TWITTER_CLIENT_ID or TWITTER_CLIENT_SECRET not set in .env file.")
        return

    auth_code, code_verifier, state = get_authorization_code()
    try:
        token_data = exchange_code_for_tokens(auth_code, code_verifier)
        print("\nSuccessfully obtained tokens:")
        print(f"TWITTER_ACCESS_TOKEN={token_data['access_token']}")
        print(f"TWITTER_REFRESH_TOKEN={token_data['refresh_token']}")
        print("\nAdd these to your .env file.")
    except requests.HTTPError as e:
        print(f"Error exchanging code for tokens: {e}")
        print(f"Response: {e.response.text}")
    except Exception as e:
        print(f"Unexpected error: {e}")

if __name__ == "__main__":
    main()