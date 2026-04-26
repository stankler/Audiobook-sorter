import logging
import re
from pathlib import Path

logger = logging.getLogger("ao")

_TOOLS = [
    {
        "name": "search_google_books",
        "description": "Search Google Books for audiobook candidates by title and optional author",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "author": {"type": "string", "description": "Leave empty if unknown"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "search_open_library",
        "description": "Look up series information for a book on Open Library",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "author": {"type": "string", "description": "Leave empty if unknown"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "identify_book",
        "description": "Return final audiobook metadata after researching",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Book title without series info"},
                "author": {"type": "string"},
                "series": {"type": "string", "description": "Series name or empty string"},
                "series_number": {"type": "number", "description": "Position in series or 0"},
            },
            "required": ["title", "author", "series", "series_number"],
        },
    },
]


async def identify_with_claude(
    folder: str,
    files: list[str],
    source_path: str,
    api_key: str,
    google_books_api_key: str = "",
) -> dict | None:
    if not api_key:
        return None

    try:
        from anthropic import AsyncAnthropic
        from pipeline.google_books import query_google_books
        from pipeline.open_library import lookup_series
    except ImportError as e:
        logger.warning("Import error in claude_identifier: %s", e)
        return None

    try:
        rel_parts = Path(folder).relative_to(source_path).parts
    except ValueError:
        rel_parts = (Path(folder).name,)

    file_names = [Path(f).name for f in files[:8]]
    path_author = (
        rel_parts[0]
        if len(rel_parts) >= 2 and not re.match(r'^#?\d', rel_parts[0])
        else None
    )

    author_instruction = (
        f"- The author is '{path_author}' — taken directly from the folder structure. Do NOT change it."
        if path_author
        else "- If author is not determinable, use 'Unknown'."
    )

    prompt = (
        "You are an audiobook metadata expert.\n"
        "Research this audiobook using the search tools, then call identify_book with the correct metadata.\n\n"
        f"Path components: {' / '.join(rel_parts)}\n"
        f"Sample files: {', '.join(file_names)}\n\n"
        "Rules:\n"
        f"{author_instruction}\n"
        "- Strip narrator names, bitrate, codec, publisher from the title.\n"
        "- Set series to empty string and series_number to 0 when not part of a series.\n"
        "- Always search before calling identify_book."
    )

    client = AsyncAnthropic(api_key=api_key)
    messages: list[dict] = [{"role": "user", "content": prompt}]

    for _ in range(6):
        try:
            response = await client.messages.create(
                model="claude-opus-4-7",
                max_tokens=2048,
                tools=_TOOLS,
                tool_choice={"type": "auto"},
                messages=messages,
            )
        except Exception as exc:
            logger.warning("Claude API error: %s", exc)
            return None

        tool_results = []

        for block in response.content:
            if getattr(block, "type", None) != "tool_use":
                continue

            name = block.name
            inp = block.input

            if name == "identify_book":
                title = inp.get("title", "").strip()
                author = inp.get("author", "").strip()
                if not title or not author:
                    return None
                series = inp.get("series", "").strip() or None
                raw_num = inp.get("series_number", 0)
                series_number: float | None = float(raw_num) if raw_num else None
                logger.info(
                    "CLAUDE_ID folder=%r → title=%r author=%r series=%r num=%r",
                    Path(folder).name, title, author, series, series_number,
                )
                return {
                    "title": title,
                    "author": author,
                    "series": series,
                    "series_number": series_number,
                }

            elif name == "search_google_books":
                q_title = inp.get("title", "")
                q_author = inp.get("author", "") or path_author or ""
                try:
                    candidates = await query_google_books(q_title, q_author, google_books_api_key)
                    content = _format_gb(candidates)
                except Exception as e:
                    content = f"Error: {e}"
                logger.info("CLAUDE_TOOL google_books title=%r → %d results", q_title, len(content.splitlines()))
                tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": content})

            elif name == "search_open_library":
                q_title = inp.get("title", "")
                q_author = inp.get("author", "") or path_author or ""
                try:
                    series = await lookup_series(q_title, q_author or None)
                    content = f"Series: {series}" if series else "No series found on Open Library"
                except Exception as e:
                    content = f"Error: {e}"
                logger.info("CLAUDE_TOOL open_library title=%r → %r", q_title, content)
                tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": content})

        if not tool_results:
            return None

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    return None


def _format_gb(candidates: list) -> str:
    if not candidates:
        return "No results found"
    lines = []
    for c in candidates[:5]:
        info = c.get("volumeInfo", {})
        title = info.get("title", "Unknown")
        subtitle = info.get("subtitle", "")
        authors = ", ".join(info.get("authors", ["Unknown"]))
        series_info = info.get("seriesInfo", {})
        vol_series = (series_info or {}).get("volumeSeries", [])
        order = vol_series[0].get("orderNumber", "") if vol_series else ""
        parts = [f"{title}" + (f": {subtitle}" if subtitle else ""), f"by {authors}"]
        if order:
            parts.append(f"book #{order} in series")
        lines.append(" — ".join(parts))
    return "\n".join(lines)
