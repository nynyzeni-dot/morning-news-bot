"""Claude APIを使って個別ニュースの深掘り解説を生成する"""

import logging
import anthropic

logger = logging.getLogger(__name__)


def generate_deepdive(item: dict, api_key: str) -> str:
    client = anthropic.Anthropic(api_key=api_key)

    prompt = f"""以下のニュースを深掘り解説してください。

タイトル：{item['title']}
ジャンル：{item['genre']}
URL：{item.get('url', '不明')}

以下のフォーマットで必ず出力してください。
見出しと内容の間は改行を入れ、各セクションの間は空行を入れてください。

①詳細サマリー
（400字程度でこのニュースの詳しい内容を説明）

②ゼニのビジネスへの影響・使えるポイント
（美容室コンサルタント・アフィリエイターとして活かせる点を具体的に。箇条書きOK）

③背景・関連する流れ
（なぜ今この話題なのか、背景や文脈を説明。箇条書きOK）

余分な前置きや後書きは不要。①から始めてください。"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    result = response.content[0].text.strip()
    logger.info(f"深掘り生成完了: ニュース#{item['number']}")
    return result
