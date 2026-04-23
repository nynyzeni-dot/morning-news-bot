"""Notionにニュースサマリーを保存する"""

import logging
from datetime import datetime, timezone, timedelta
from notion_client import Client

logger = logging.getLogger(__name__)
JST = timezone(timedelta(hours=9))
NEWS_DB_ID = "34baecda-34b7-818d-afad-ddbbf3e6a30e"


def _get_title_property(client: Client, db_id: str) -> str:
    """DBのtitleプロパティ名を動的に取得する"""
    try:
        db = client.databases.retrieve(database_id=db_id)
        props = db.get("properties") or {}
        for name, prop in props.items():
            if isinstance(prop, dict) and prop.get("type") == "title":
                return name
    except Exception:
        pass
    return "タイトル"


def _make_blocks(news_by_genre: dict[str, list[dict]], script: str) -> list[dict]:
    blocks: list[dict] = []

    for genre, items in news_by_genre.items():
        if not items:
            continue
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": genre}}]
            },
        })
        for item in items:
            title = item["title"]
            link = item.get("link", "")
            if link:
                blocks.append({
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{
                            "type": "text",
                            "text": {"content": title, "link": {"url": link}},
                        }]
                    },
                })
            else:
                blocks.append({
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{"type": "text", "text": {"content": title}}]
                    },
                })

    blocks.append({"object": "block", "type": "divider", "divider": {}})
    blocks.append({
        "object": "block",
        "type": "heading_2",
        "heading_2": {
            "rich_text": [{"type": "text", "text": {"content": "ラジオ原稿"}}]
        },
    })

    # Notionブロックは1件2000文字制限なので分割
    for chunk in [script[i:i+1900] for i in range(0, len(script), 1900)]:
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": chunk}}]
            },
        })

    return blocks


def save_to_notion(script: str, news_by_genre: dict[str, list[dict]], api_key: str) -> str:
    """Notionにページを作成してURLを返す"""
    client = Client(auth=api_key)
    today = datetime.now(JST)
    title = f"朝のニュース {today.strftime('%Y/%m/%d')}"

    title_prop = _get_title_property(client, NEWS_DB_ID)
    blocks = _make_blocks(news_by_genre, script)

    page = client.pages.create(
        parent={"database_id": NEWS_DB_ID},
        properties={
            title_prop: {
                "title": [{"text": {"content": title}}]
            },
            "日付": {
                "date": {"start": today.strftime("%Y-%m-%d")}
            },
        },
        children=blocks,
    )
    url = page.get("url", "")
    logger.info(f"Notion保存完了: {url}")
    return url
