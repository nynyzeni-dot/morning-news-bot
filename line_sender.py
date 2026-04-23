"""LINE Messaging APIでメッセージと音声を送信する"""

import logging
import httpx

logger = logging.getLogger(__name__)
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"


def send_news(
    user_id: str,
    token: str,
    text: str,
    audio_url: str,
    duration_ms: int,
) -> None:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "to": user_id,
        "messages": [
            {
                "type": "text",
                "text": text,
            },
            {
                "type": "audio",
                "originalContentUrl": audio_url,
                "duration": duration_ms,
            },
        ],
    }

    resp = httpx.post(LINE_PUSH_URL, json=payload, headers=headers, timeout=30)

    if resp.status_code != 200:
        logger.error(f"LINE送信失敗: {resp.status_code} {resp.text}")
        resp.raise_for_status()

    logger.info("LINE送信完了")
