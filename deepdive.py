"""Claude APIを使って個別ニュースの深掘り解説を生成する"""

import logging
import anthropic

logger = logging.getLogger(__name__)


def generate_deepdive(item: dict, api_key: str) -> str:
    client = anthropic.Anthropic(api_key=api_key)

    prompt = f"""以下のニュースについて深掘り解説をしてください。

【ニュース情報】
番号：{item['number']}
ジャンル：{item['genre']}
タイトル：{item['title']}
URL：{item.get('url', '不明')}

以下の3点を日本語で解説してください。

①【詳細サマリー】（400字程度）
このニュースの詳しい内容を説明してください。

②【ゼニのビジネスへの影響・使えるポイント】
美容室コンサルタント・アフィリエイターとして活かせる点を具体的に。

③【背景・関連する流れ】
なぜ今この話題が注目されているのか、背景や文脈を説明してください。

箇条書きOK。わかりやすく書いてください。"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    result = response.content[0].text.strip()
    logger.info(f"深掘り生成完了: ニュース#{item['number']}")
    return result
