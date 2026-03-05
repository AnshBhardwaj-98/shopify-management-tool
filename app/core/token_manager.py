import time
import requests
from app.core.config import settings

class TokenManager:

    def __init__(self):
        self.access_token = None
        self.expiry = 0

    def get_token(self):

        if self.access_token and time.time() < self.expiry:
            return self.access_token

        return self.refresh_token()

    def refresh_token(self):

        url = f"https://{settings.SHOPIFY_STORE}/admin/oauth/access_token"

        payload = {
            "grant_type": "client_credentials",
            "client_id": settings.SHOPIFY_CLIENT_ID,
            "client_secret": settings.SHOPIFY_CLIENT_SECRET
        }

        response = requests.post(url, data=payload)

        if response.status_code != 200:
            raise Exception(
                f"Token request failed: {response.status_code} | {response.text}"
            )

        try:
            data = response.json()
        except Exception:
            raise Exception(
                f"Token response not JSON: {response.text}"
            )

        self.access_token = data["access_token"]
        self.expiry = time.time() + data["expires_in"] - 60

        return self.access_token


token_manager = TokenManager()