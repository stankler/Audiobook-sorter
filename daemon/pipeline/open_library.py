import logging
import httpx

logger = logging.getLogger("ao")
_cache: dict[str, str | None] = {}
_search_cache: dict[str, list[dict]] = {}


async def search_books(title: str, author: str | None) -> list[dict]:
    """Search Open Library and return normalized candidates."""
    key = f"search|{title}|{author or ''}"
    if key in _search_cache:
        return _search_cache[key]

    params = {"title": title, "fields": "title,author_name,series,series_number", "limit": 5}
    if author:
        params["author"] = author

    results = []
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get("https://openlibrary.org/search.json", params=params)
            r.raise_for_status()
            docs = r.json().get("docs", [])
            logger.info("OL_QUERY title=%r author=%r → %d results", title, author, len(docs))
            for doc in docs[:5]:
                ol_title = doc.get("title", "")
                authors = doc.get("author_name", [])
                series_list = doc.get("series", [])
                series_numbers = doc.get("series_number", [])
                series = series_list[0] if series_list else None
                try:
                    series_number = float(series_numbers[0]) if series_numbers else None
                except (ValueError, TypeError):
                    series_number = None
                logger.info("  OL_RESULT title=%r author=%r series=%r", ol_title, authors[:1], series)
                results.append({
                    "title": ol_title,
                    "author": authors[0] if authors else "Unknown",
                    "series": series,
                    "series_number": series_number,
                })
    except Exception as e:
        logger.warning("Open Library search failed title=%r: %s", title, e)

    _search_cache[key] = results
    return results


async def lookup_series(title: str, author: str | None) -> str | None:
    key = f"{title}|{author or ''}"
    if key in _cache:
        return _cache[key]

    params = {"title": title, "fields": "title,series", "limit": 5}
    if author:
        params["author"] = author

    result = None
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get("https://openlibrary.org/search.json", params=params)
            r.raise_for_status()
            for doc in r.json().get("docs", []):
                series_list = doc.get("series", [])
                if series_list:
                    result = series_list[0]
                    break
    except Exception as e:
        import logging
        logging.getLogger("ao").warning("Open Library lookup failed title=%r: %s", title, e)

    _cache[key] = result
    return result
