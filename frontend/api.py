"""HTTP client for the personal AI backend."""
from __future__ import annotations

import httpx
from config import API_BASE_URL


class APIClient:
    def __init__(self):
        self._access_token: str | None = None
        self._refresh_token: str | None = None

    @property
    def is_authenticated(self) -> bool:
        return self._access_token is not None

    def login(self, username: str, password: str) -> bool:
        try:
            r = httpx.post(
                f"{API_BASE_URL}/auth/login",
                json={"username": username, "password": password},
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                self._access_token = data["access_token"]
                self._refresh_token = data["refresh_token"]
                return True
            return False
        except httpx.ConnectError:
            raise ConnectionError("Cannot connect to backend. Is the server running?")

    def _refresh(self) -> bool:
        if not self._refresh_token:
            return False
        try:
            r = httpx.post(
                f"{API_BASE_URL}/auth/refresh",
                json={"refresh_token": self._refresh_token},
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                self._access_token = data["access_token"]
                self._refresh_token = data["refresh_token"]
                return True
            return False
        except Exception:
            return False

    def send_message(self, message: str, history: list[dict]) -> str:
        headers = {"Authorization": f"Bearer {self._access_token}"}
        payload = {"message": message, "history": history}

        r = httpx.post(
            f"{API_BASE_URL}/chat",
            json=payload,
            headers=headers,
            timeout=120,
        )

        if r.status_code == 401:
            if self._refresh():
                headers["Authorization"] = f"Bearer {self._access_token}"
                r = httpx.post(
                    f"{API_BASE_URL}/chat",
                    json=payload,
                    headers=headers,
                    timeout=120,
                )
            else:
                self._access_token = None
                raise PermissionError("Session expired. Please log in again.")

        if r.status_code != 200:
            raise RuntimeError(f"Backend error {r.status_code}: {r.text}")

        return r.json()["response"]

    def logout(self):
        self._access_token = None
        self._refresh_token = None


client = APIClient()