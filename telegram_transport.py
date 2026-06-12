"""
TelegramTransport — wysyłanie i odbieranie zaszyfrowanych wiadomości przez Telegram Bot API.

Każdy użytkownik ma własnego bota (token z BotFather).
Bot służy wyłącznie jako "listonosz" — przesyła zaszyfrowane blobs, nie zna treści.

Architektura:
  - send()     → POST /sendMessage  (synchroniczne, przez httpx)
  - start_polling() → uruchamia wątek pobierający nowe wiadomości co POLL_INTERVAL sekund
  - stop_polling()  → zatrzymuje wątek
  - on_message  → callback wywoływany gdy przyjdzie nowa wiadomość: (chat_id, text)
"""

import threading
import time
import logging
import httpx
from typing import Callable

logger = logging.getLogger(__name__)

POLL_INTERVAL = 3       # sekundy między kolejnymi getUpdates
REQUEST_TIMEOUT = 10    # timeout pojedynczego żądania HTTP


class TelegramTransport:
    BASE = "https://api.telegram.org/bot{token}/{method}"

    def __init__(self, bot_token: str):
        self.token = bot_token.strip()
        self._last_update_id: int = 0
        self._polling_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        # callback(chat_id: str, text: str) wywoływany w wątku pollingu
        self.on_message: Callable[[str, str], None] | None = None

    # ──────────────────────────────────────────────────────────────
    # API helpers
    # ──────────────────────────────────────────────────────────────

    def _url(self, method: str) -> str:
        return self.BASE.format(token=self.token, method=method)

    def _post(self, method: str, payload: dict) -> dict:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            r = client.post(self._url(method), json=payload)
            r.raise_for_status()
            return r.json()

    def _get(self, method: str, params: dict | None = None) -> dict:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            r = client.get(self._url(method), params=params or {})
            r.raise_for_status()
            return r.json()

    # ──────────────────────────────────────────────────────────────
    # Publiczne API
    # ──────────────────────────────────────────────────────────────

    def validate_token(self) -> dict:
        """
        Sprawdź poprawność tokena — wywołaj getMe.
        Zwraca słownik z danymi bota lub rzuca wyjątek.
        """
        data = self._get("getMe")
        if not data.get("ok"):
            raise ValueError(f"Token nieprawidłowy: {data}")
        return data["result"]

    def send(self, chat_id: str, text: str) -> dict:
        """
        Wyślij wiadomość tekstową do chat_id.
        chat_id może być numerycznym ID lub @username.
        Zwraca odpowiedź API lub rzuca wyjątek przy błędzie.
        """
        if not chat_id:
            raise ValueError("chat_id nie może być pusty.")
        if not text:
            raise ValueError("Wiadomość nie może być pusta.")

        payload = {
            "chat_id": chat_id,
            "text": text,
            # wyłączone podglądy linków — wiadomość to zaszyfrowany blob
            "disable_web_page_preview": True,
        }
        result = self._post("sendMessage", payload)
        if not result.get("ok"):
            raise RuntimeError(f"Telegram API error: {result}")
        return result

    def get_my_chat_id(self) -> str | None:
        """
        Zwróć chat_id ostatniej osoby która napisała do bota.
        Przydatne przy pierwszym uruchomieniu — użytkownik pisze /start,
        a aplikacja odczytuje jego chat_id.
        """
        data = self._get("getUpdates", {"limit": 1, "offset": -1})
        updates = data.get("result", [])
        if not updates:
            return None
        msg = updates[-1].get("message", {})
        chat = msg.get("chat", {})
        return str(chat.get("id", ""))

    # ──────────────────────────────────────────────────────────────
    # Polling
    # ──────────────────────────────────────────────────────────────

    def start_polling(self) -> None:
        """Uruchom wątek pobierający nowe wiadomości w tle."""
        if self._polling_thread and self._polling_thread.is_alive():
            return
        self._stop_event.clear()
        self._polling_thread = threading.Thread(
            target=self._poll_loop, daemon=True, name="TelegramPoller"
        )
        self._polling_thread.start()
        logger.info("Telegram polling started.")

    def stop_polling(self) -> None:
        """Zatrzymaj wątek pollingu."""
        self._stop_event.set()
        if self._polling_thread:
            self._polling_thread.join(timeout=REQUEST_TIMEOUT + 2)
        logger.info("Telegram polling stopped.")

    @property
    def is_polling(self) -> bool:
        return bool(self._polling_thread and self._polling_thread.is_alive())

    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._fetch_updates()
            except Exception as e:
                logger.warning(f"Polling error: {e}")
            self._stop_event.wait(POLL_INTERVAL)

    def _fetch_updates(self) -> None:
        params = {
            "offset": self._last_update_id + 1,
            "timeout": 0,
            "allowed_updates": ["message"],
        }
        data = self._get("getUpdates", params)
        for update in data.get("result", []):
            uid = update.get("update_id", 0)
            if uid > self._last_update_id:
                self._last_update_id = uid
            self._handle_update(update)

    def _handle_update(self, update: dict) -> None:
        msg = update.get("message")
        if not msg:
            return
        text = msg.get("text", "").strip()
        chat_id = str(msg.get("chat", {}).get("id", ""))
        if text and chat_id and self.on_message:
            self.on_message(chat_id, text)
