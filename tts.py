"""Google Cloud Text-to-Speech REST APIで音声ファイルを生成する"""

import base64
import logging
import httpx
from api_monitor import track_tts_chars

logger = logging.getLogger(__name__)

TTS_ENDPOINT = "https://texttospeech.googleapis.com/v1/text:synthesize"

# MP3 32kbps = 4000 bytes/sec（目安）
MP3_BYTES_PER_SEC = 4000


def synthesize_speech(text: str, api_key: str, output_path: str) -> int:
    """テキストをMP3ファイルに変換。durationをミリ秒で返す。"""
    payload = {
        "input": {"text": text},
        "voice": {
            "languageCode": "ja-JP",
            "name": "ja-JP-Neural2-B",
        },
        "audioConfig": {
            "audioEncoding": "MP3",
            "speakingRate": 1.1,
        },
    }

    resp = httpx.post(
        f"{TTS_ENDPOINT}?key={api_key}",
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()

    audio_bytes = base64.b64decode(resp.json()["audioContent"])

    with open(output_path, "wb") as f:
        f.write(audio_bytes)

    duration_ms = int(len(audio_bytes) / MP3_BYTES_PER_SEC * 1000)
    logger.info(f"音声生成完了: {len(audio_bytes):,} bytes, 推定 {duration_ms // 1000}秒")
    track_tts_chars(len(text))
    return duration_ms
