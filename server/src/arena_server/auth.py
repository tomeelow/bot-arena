"""GitHub login and signed session cookies.

We keep a GitHub id and handle, nothing else: the access token is used once, to ask GitHub
who the user is, and dropped.
"""

import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlencode

import httpx

GITHUB_AUTHORIZE = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN = "https://github.com/login/oauth/access_token"
GITHUB_USER = "https://api.github.com/user"


class GitHub(Protocol):
    def authorize_url(self, state: str) -> str: ...
    def identify(self, code: str) -> tuple[int, str]: ...  # (GitHub id, login)


@dataclass(frozen=True)
class GitHubOAuth:
    client_id: str
    client_secret: str

    def authorize_url(self, state: str) -> str:
        # No scopes: a user's public id and login are all we need.
        return f"{GITHUB_AUTHORIZE}?{urlencode({'client_id': self.client_id, 'state': state})}"

    def identify(self, code: str) -> tuple[int, str]:
        token = httpx.post(
            GITHUB_TOKEN,
            data={"client_id": self.client_id, "client_secret": self.client_secret, "code": code},
            headers={"Accept": "application/json"},
            timeout=10,
        ).json()["access_token"]
        user = httpx.get(
            GITHUB_USER,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            timeout=10,
        ).json()
        return int(user["id"]), str(user["login"])


class Sessions:
    """`<user id>.<issued at>.<hmac>`: tamper-evident and self-expiring, no session table."""

    def __init__(self, secret: bytes, max_age_s: int) -> None:
        if len(secret) < 32:
            raise ValueError("SESSION_SECRET must be at least 32 bytes")
        self.secret = secret
        self.max_age_s = max_age_s

    def issue(self, user_id: int) -> str:
        payload = f"{user_id}.{int(time.time())}"
        return f"{payload}.{self._sign(payload)}"

    def verify(self, cookie: str | None) -> int | None:
        if not cookie or cookie.count(".") != 2:
            return None
        user, issued, signature = cookie.split(".")
        if not hmac.compare_digest(signature, self._sign(f"{user}.{issued}")):
            return None
        if not (user.isdigit() and issued.isdigit()):
            return None
        if time.time() - int(issued) > self.max_age_s:
            return None
        return int(user)

    def _sign(self, payload: str) -> str:
        return hmac.new(self.secret, payload.encode(), hashlib.sha256).hexdigest()
