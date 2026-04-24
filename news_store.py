"""当日配信したニュースリストを一時保存する"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)
_STORE = Path("/data/morning_news_today.json") if Path("/data").exists() else Path("/tmp/morning_news_today.json")


def save_news(items: list[dict]) -> None:
    _STORE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"ニュースリスト保存: {len(items)}件")


def load_news() -> list[dict]:
    if not _STORE.exists():
        return []
    try:
        return json.loads(_STORE.read_text(encoding="utf-8"))
    except Exception:
        return []
