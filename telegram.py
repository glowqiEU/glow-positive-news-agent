import os
import requests


MAX_TELEGRAM_TEXT_LENGTH = 4096


class PublishingNotApprovedError(RuntimeError):
    """Raised when a process tries to publish without an explicit approval gate."""


def publishing_is_approved() -> bool:
    """Require two independent, explicit switches before any Telegram write."""
    dry_run = os.getenv("DRY_RUN", "true").strip().lower()
    approval = os.getenv("PUBLISH_APPROVED", "false").strip().lower()
    return dry_run == "false" and approval == "true"


def send_telegram_message(text: str) -> None:
    if not publishing_is_approved():
        raise PublishingNotApprovedError(
            "Telegram publishing is locked. Set DRY_RUN=false and "
            "PUBLISH_APPROVED=true only after explicit editorial approval."
        )
    if not text.strip():
        raise ValueError("Refusing to publish an empty Telegram message")
    if len(text) > MAX_TELEGRAM_TEXT_LENGTH:
        raise ValueError(
            f"Telegram message is {len(text)} characters; maximum is "
            f"{MAX_TELEGRAM_TEXT_LENGTH}"
        )

    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHANNEL_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    response = requests.post(
        url,
        json={
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": False,
        },
        timeout=30,
    )
    response.raise_for_status()
