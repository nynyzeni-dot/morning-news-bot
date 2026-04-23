"""Claude APIを使って朝のラジオニュース原稿を生成する"""

import logging
from datetime import datetime, timezone, timedelta
import anthropic

logger = logging.getLogger(__name__)
JST = timezone(timedelta(hours=9))

SYSTEM_PROMPT = """あなたはラジオパーソナリティです。毎朝リスナーに今日のニュースを届けるラジオ番組の原稿を書きます。
- テンポよく、聞いていて心地よい日本語で書いてください
- 各ニュースは1〜2行で簡潔に要約してください
- ジャルゴンや難しい言葉は避け、通勤中でも頭に入る平易な表現を使ってください
- 原稿のみを出力してください（余分な説明・タグ不要）"""


def generate_script(
    news_by_genre: dict[str, list[dict]],
    numbered_news: list[dict],
    api_status: str | None = None,
) -> str:
    client = anthropic.Anthropic()
    now = datetime.now(JST)
    today = f"{now.month}月{now.day}日"

    news_lines = ""
    for item in numbered_news:
        news_lines += f"{item['number']}. 【{item['genre']}】{item['title']}\n"

    api_status_section = ""
    if api_status:
        api_status_section = f"\n- 冒頭の挨拶の直後に次のAPI残高情報を読み上げる（自然な話し言葉に変換）:\n{api_status}\n"

    prompt = f"""以下のニュース見出しをもとに、朝のラジオニュース原稿を作成してください。

【収集したニュース見出し（番号付き）】
{news_lines}

【作成要件】
- 冒頭: 「おはようございます、ゼニさん。今日{today}のニュースをお届けします。」{api_status_section}
- 各ニュースを「1つ目は〜」「2つ目は〜」のように通し番号で紹介する
- ジャンルの切り替え時に「続いて○○関連のニュースです。」などの区切りを入れる
- 末尾: 「以上、今日のニュースでした。気になるニュースがあれば番号をLINEに送ってください。詳しく解説します。いってらっしゃい！」
- 全体800〜1000文字（3〜4分で読める長さ）
- ラジオで読み上げる自然な文体で"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    script = response.content[0].text.strip()
    logger.info(f"原稿生成完了: {len(script)}文字")
    return script
