"""API残高・使用量の取得モジュール"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)
JST = timezone(timedelta(hours=9))

_TTS_FILE = Path("/tmp/tts_monthly.json")
TTS_FREE_LIMIT = 4_000_000  # 月400万文字（Neural2ボイス無料枠）


# ─── Google TTS：ローカルトラッキング ─────────────────────────

def track_tts_chars(char_count: int) -> None:
    """TTS呼び出し時に文字数を蓄積する（月次リセット付き）"""
    month = datetime.now(JST).strftime("%Y-%m")
    data = _load_tts_data()
    if data.get("month") != month:
        data = {"month": month, "chars": 0}
    data["chars"] += char_count
    _TTS_FILE.write_text(json.dumps(data), encoding="utf-8")


def get_tts_usage() -> dict:
    """今月のTTS使用文字数を返す"""
    month = datetime.now(JST).strftime("%Y-%m")
    data = _load_tts_data()
    if data.get("month") != month:
        return {"chars": 0, "month": month}
    return data


def _load_tts_data() -> dict:
    try:
        if _TTS_FILE.exists():
            return json.loads(_TTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


# ─── Anthropic ────────────────────────────────────────────────

def fetch_anthropic_usage(api_key: str) -> dict | None:
    """今月のAnthropicトークン使用量を取得"""
    try:
        now = datetime.now(JST)
        start = now.strftime("%Y-%m-01T00:00:00Z")
        resp = httpx.get(
            "https://api.anthropic.com/v1/organizations/usage",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            params={"start_time": start, "limit": 1000},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
        logger.warning(f"Anthropic usage API: {resp.status_code}")
        return None
    except Exception as e:
        logger.warning(f"Anthropic usage取得失敗: {e}")
        return None


def _calc_anthropic_cost_jpy(data: dict) -> float | None:
    """usageデータからコスト（円）を推計する"""
    try:
        # APIが直接cost_usdを返す場合
        if "total_cost" in data:
            usd = float(data["total_cost"])
            return usd * 150
        # usageリストを合算する場合
        items = data.get("data") or data.get("usage") or []
        total_input = sum(i.get("input_tokens", 0) for i in items)
        total_output = sum(i.get("output_tokens", 0) for i in items)
        # claude-sonnet-4-6: $3/MTok入力, $15/MTok出力
        usd = (total_input * 3 + total_output * 15) / 1_000_000
        return usd * 150
    except Exception:
        return None


# ─── Railway ──────────────────────────────────────────────────

def fetch_railway_usage(token: str) -> dict | None:
    """Railway GraphQL APIで今月の使用量($)を取得"""
    query = """
    query {
      me {
        usage {
          estimatedUsage
        }
      }
    }
    """
    try:
        resp = httpx.post(
            "https://backboard.railway.app/graphql/v2",
            json={"query": query},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
        logger.warning(f"Railway API: {resp.status_code}")
        return None
    except Exception as e:
        logger.warning(f"Railway usage取得失敗: {e}")
        return None


def _parse_railway_usage(data: dict) -> float | None:
    try:
        return float(data["data"]["me"]["usage"]["estimatedUsage"])
    except Exception:
        return None


# ─── ステータスブロック生成 ────────────────────────────────────

def build_status_block(api_key: str, railway_token: str | None) -> str:
    """朝通知に挿入する【今月のAPI残高】ブロックを生成"""
    lines = ["【今月のAPI残高】"]

    # Claude
    anthropic_data = fetch_anthropic_usage(api_key)
    if anthropic_data is not None:
        cost_jpy = _calc_anthropic_cost_jpy(anthropic_data)
        if cost_jpy is not None:
            warn = "⚠️ " if cost_jpy >= (10_000 - 3_000) else ""  # 残り3,000円以下で警告
            lines.append(f"・Claude：{warn}今月約{int(cost_jpy):,}円使用")
        else:
            lines.append("・Claude：取得済み（金額計算不可）")
    else:
        lines.append("・Claude：取得不可")

    # Google TTS
    tts = get_tts_usage()
    chars_used = tts.get("chars", 0)
    chars_remaining = max(TTS_FREE_LIMIT - chars_used, 0)
    warn_tts = "⚠️ " if chars_remaining < 200_000 else ""
    lines.append(
        f"・Google TTS：{warn_tts}{chars_used // 10_000}万文字使用済み"
        f"（残り{chars_remaining // 10_000}万文字）"
    )

    # Railway
    if railway_token:
        railway_data = fetch_railway_usage(railway_token)
        if railway_data is not None:
            usage_usd = _parse_railway_usage(railway_data)
            if usage_usd is not None:
                remaining = max(5.0 - usage_usd, 0)
                warn_r = "⚠️ " if remaining < 1.0 else ""
                lines.append(f"・Railway：{warn_r}今月${usage_usd:.2f}使用（残り${remaining:.2f}）")
            else:
                lines.append("・Railway：取得済み（解析不可）")
        else:
            lines.append("・Railway：取得不可")
    else:
        lines.append("・Railway：APIトークン未設定")

    return "\n".join(lines)
