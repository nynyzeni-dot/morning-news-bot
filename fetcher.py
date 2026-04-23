"""Google News RSSからニュースを収集する"""

import urllib.request
import urllib.parse
from xml.etree import ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
import logging

logger = logging.getLogger(__name__)
JST = timezone(timedelta(hours=9))

GENRES: dict[str, list[str]] = {
    "美容室業界": ["美容室 経営", "美容師 離職", "美容室 採用", "ヘアサロン トレンド"],
    "コンサル・組織・マネジメント": ["スタッフ定着", "組織マネジメント", "人材育成 美容", "離職防止"],
    "AI最新ニュース": ["AI 最新", "ChatGPT", "Claude AI", "生成AI ビジネス活用"],
    "アフィリエイト・メディア運営": ["アフィリエイト 稼ぎ方", "ブログ収益化", "SEO 最新"],
}

RSS_BASE = "https://news.google.com/rss/search?q={q}&hl=ja&gl=JP&ceid=JP:ja"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"}


def fetch_genre(genre: str, keywords: list[str], max_items: int = 3) -> list[dict]:
    seen_titles: set[str] = set()
    items: list[dict] = []
    cutoff = datetime.now(JST) - timedelta(hours=48)

    for keyword in keywords:
        if len(items) >= max_items:
            break
        url = RSS_BASE.format(q=urllib.parse.quote(keyword))
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=15) as resp:
                xml_data = resp.read()
            root = ET.fromstring(xml_data)

            for item in root.findall(".//item"):
                title = (item.findtext("title") or "").strip()
                link = item.findtext("link") or ""
                pub_date_str = item.findtext("pubDate") or ""

                if not title or title in seen_titles:
                    continue

                # 48時間以内の記事のみ
                try:
                    pub_dt = parsedate_to_datetime(pub_date_str).astimezone(JST)
                    if pub_dt < cutoff:
                        continue
                except Exception:
                    pass  # 日付不明は通過させる

                seen_titles.add(title)
                items.append({"title": title, "link": link, "genre": genre})
                if len(items) >= max_items:
                    break

        except Exception as e:
            logger.warning(f"RSS取得失敗 [{keyword}]: {e}")

    return items[:max_items]


def fetch_all_news() -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for genre, keywords in GENRES.items():
        items = fetch_genre(genre, keywords)
        result[genre] = items
        logger.info(f"  {genre}: {len(items)}件取得")
    return result
