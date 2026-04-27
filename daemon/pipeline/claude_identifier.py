import json
import logging

logger = logging.getLogger("ao")


async def find_series(title: str, author: str, api_key: str) -> tuple[str | None, float | None]:
    """Ask Claude what series a book belongs to. Returns (series, series_number) or (None, None)."""
    if not api_key or not title:
        return None, None

    try:
        from anthropic import AsyncAnthropic
    except ImportError:
        return None, None

    client = AsyncAnthropic(api_key=api_key, timeout=30.0)
    prompt = (
        f'What book series does "{title}" by {author} belong to?\n\n'
        'Reply with JSON only, no other text:\n'
        '{"series": "Series Name", "number": 1}\n'
        'If not part of a series: {"series": null, "number": null}'
    )

    try:
        msg = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        data = json.loads(text)
        series = data.get("series") or None
        number = data.get("number")
        series_number = float(number) if number is not None else None
        logger.info("CLAUDE_SERIES title=%r author=%r → series=%r number=%r", title, author, series, series_number)
        return series, series_number
    except Exception as e:
        logger.warning("Claude series lookup failed title=%r: %s", title, e)
        return None, None
