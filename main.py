"""朝のニュース自動収集・音声化・LINE配信システム

起動: uvicorn main:app --host 0.0.0.0 --port $PORT
毎朝6:30 JSTに自動実行。/run エンドポイントで手動実行可能。
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse

from api_monitor import build_status_block
from deepdive import generate_deepdive
from fetcher import fetch_all_news
from generator import generate_script
from line_sender import send_news, send_text
from news_store import load_news, save_news
from notion_saver import save_to_notion
from tts import synthesize_speech

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))
# /data はRailwayの永続ボリューム。未設定時は/tmpにフォールバック
_VOLUME = Path(os.environ.get("AUDIO_VOLUME_PATH", "/data/audio"))
try:
    _VOLUME.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR = _VOLUME
except OSError:
    import tempfile
    AUDIO_DIR = Path(tempfile.gettempdir()) / "morning_news_audio"
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    logger.warning(f"ボリューム作成失敗。/tmpにフォールバック: {AUDIO_DIR}")

app = FastAPI(title="Morning News Bot")


# ─────────────────────────────────────────
# ルート
# ─────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.now(JST).isoformat()}


@app.get("/audio/{filename}")
async def serve_audio(filename: str):
    """LINE Messaging APIが音声URLにアクセスする際に使用"""
    # パストラバーサル防止
    if "/" in filename or "\\" in filename or not filename.endswith(".mp3"):
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = AUDIO_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Audio not found")
    return FileResponse(path, media_type="audio/mpeg")


@app.post("/run")
@app.get("/run")
async def run_manual(background_tasks: BackgroundTasks):
    """手動実行（テスト・緊急時用）"""
    background_tasks.add_task(run_morning_news)
    return {"status": "started", "message": "朝のニュース配信を開始しました"}


FORWARD_WEBHOOK_URL = "https://musubihira-company-production.up.railway.app/callback"


@app.post("/webhook")
async def line_webhook(request: Request, background_tasks: BackgroundTasks):
    """LINE Webhookエンドポイント：番号受信で深掘り配信、それ以外は既存botへ転送"""
    raw_body = await request.body()
    headers = {k: v for k, v in request.headers.items() if k.lower() != "host"}

    body = await request.json() if raw_body else {}
    handled = False

    for event in body.get("events", []):
        if event.get("type") == "message":
            msg = event.get("message", {})
            if msg.get("type") == "text":
                text = msg.get("text", "").strip()
                if text.isdigit() and 1 <= int(text) <= 12:
                    background_tasks.add_task(_handle_deepdive, int(text))
                    handled = True

    if not handled:
        background_tasks.add_task(_forward_webhook, raw_body, headers)

    return {"status": "ok"}


async def _forward_webhook(raw_body: bytes, headers: dict) -> None:
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(FORWARD_WEBHOOK_URL, content=raw_body, headers=headers)
    except Exception as e:
        logger.warning(f"Webhook転送失敗: {e}")


# ─────────────────────────────────────────
# メイン処理
# ─────────────────────────────────────────

def _build_numbered_news(news_by_genre: dict[str, list[dict]]) -> list[dict]:
    numbered = []
    n = 1
    for genre, items in news_by_genre.items():
        for item in items:
            numbered.append({
                "number": n,
                "genre": genre,
                "title": item["title"],
                "url": item.get("link", ""),
            })
            n += 1
    return numbered


async def _handle_deepdive(number: int) -> None:
    anthropic_key = os.environ["ANTHROPIC_API_KEY"]
    line_token = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
    line_user = os.environ["LINE_USER_ID_ZENI"]

    items = load_news()
    if not items:
        send_text(line_user, line_token, "今日のニュースリストが見つかりませんでした。朝の配信後に番号を送ってください。")
        return

    item = next((i for i in items if i["number"] == number), None)
    if not item:
        send_text(line_user, line_token, f"番号{number}のニュースは見つかりませんでした（今日は{len(items)}件）。")
        return

    try:
        send_text(line_user, line_token, f"【{number}】{item['title']}\n\n深掘り中... 少々お待ちください🔍")
        result = await asyncio.to_thread(generate_deepdive, item, anthropic_key)
        send_text(line_user, line_token, result)
    except Exception as e:
        logger.error(f"深掘りエラー: {e}", exc_info=True)
        send_text(line_user, line_token, f"深掘り生成でエラーが発生しました。\n{e}")


async def run_morning_news() -> None:
    logger.info("=" * 50)
    logger.info("朝のニュース配信 開始")
    logger.info("=" * 50)

    # 環境変数
    anthropic_key = os.environ["ANTHROPIC_API_KEY"]
    tts_key = os.environ["GOOGLE_TTS_API_KEY"]
    line_token = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
    line_user = os.environ["LINE_USER_ID_ZENI"]
    notion_key = os.environ["NOTION_API_KEY"]
    railway_token = os.environ.get("RAILWAY_API_TOKEN")
    app_url = os.environ.get("APP_URL", "").rstrip("/")

    if not app_url:
        raise ValueError("APP_URL が設定されていません。RailwayのパブリックURLを設定してください。")

    now_jst = datetime.now(JST)
    today_str = f"{now_jst.month}月{now_jst.day}日"
    audio_path: Path | None = None

    try:
        # Step 1: API残高取得
        logger.info("[Step 1] API残高取得中...")
        api_status = await asyncio.to_thread(build_status_block, anthropic_key, railway_token)
        logger.info(f"  {api_status.splitlines()[0]}")

        # Step 2: ニュース収集
        logger.info("[Step 2] ニュース収集中...")
        news_by_genre = await asyncio.to_thread(fetch_all_news)
        total = sum(len(v) for v in news_by_genre.values())
        logger.info(f"  合計 {total} 件取得")
        numbered_news = _build_numbered_news(news_by_genre)
        save_news(numbered_news)

        # Step 3: 原稿生成（Claude API）
        logger.info("[Step 3] 原稿生成中 (Claude API)...")
        script = await asyncio.to_thread(generate_script, news_by_genre, numbered_news, api_status)

        # Step 4: 音声生成（Google TTS）
        logger.info("[Step 4] 音声生成中 (Google TTS)...")
        filename = f"{uuid.uuid4().hex}.mp3"
        audio_path = AUDIO_DIR / filename
        duration_ms = await asyncio.to_thread(
            synthesize_speech, script, tts_key, str(audio_path)
        )

        # Step 5: LINE送信
        logger.info("[Step 5] LINE送信中...")
        audio_url = f"{app_url}/audio/{filename}"
        text_msg = (
            f"{api_status}\n\n"
            f"おはようございます！\n"
            f"今日（{today_str}）の朝ニュース音声が届きました 🎙️\n"
            f"下の音声を再生してください。"
        )
        await asyncio.to_thread(
            send_news, line_user, line_token, text_msg, audio_url, duration_ms
        )

        # Step 6: Notion保存
        logger.info("[Step 6] Notion保存中...")
        notion_url = await asyncio.to_thread(
            save_to_notion, script, news_by_genre, notion_key
        )
        logger.info(f"  Notion: {notion_url}")

        logger.info("=" * 50)
        logger.info("朝のニュース配信 完了")
        logger.info("=" * 50)

    except Exception as e:
        logger.error(f"配信エラー: {e}", exc_info=True)
        # エラー時もLINEにテキスト通知を試みる
        try:
            import httpx
            httpx.post(
                "https://api.line.me/v2/bot/message/push",
                json={
                    "to": line_user,
                    "messages": [{"type": "text", "text": f"⚠️ 朝ニュース配信でエラーが発生しました。\n{e}"}],
                },
                headers={"Authorization": f"Bearer {line_token}"},
                timeout=10,
            )
        except Exception:
            pass
    finally:
        # 前日以前の古い音声ファイルを削除（当日分は保持）
        _cleanup_old_audio(audio_path)


def _cleanup_old_audio(current_path: Path | None = None) -> None:
    """24時間以上前の音声ファイルを削除する"""
    now = datetime.now(JST)
    count = 0
    for f in AUDIO_DIR.glob("*.mp3"):
        if current_path and f == current_path:
            continue
        age_hours = (now.timestamp() - f.stat().st_mtime) / 3600
        if age_hours > 24:
            f.unlink(missing_ok=True)
            count += 1
    if count:
        logger.info(f"古い音声ファイル {count} 件削除")


# ─────────────────────────────────────────
# スタートアップ
# ─────────────────────────────────────────

@app.on_event("startup")
async def startup() -> None:
    scheduler = AsyncIOScheduler(timezone="Asia/Tokyo")
    scheduler.add_job(
        run_morning_news,
        CronTrigger(hour=6, minute=30, timezone="Asia/Tokyo"),
        id="morning_news",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("スケジューラー開始: 毎朝 6:30 JST に自動実行")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
