import httpx

_cache: dict[str, str | None] = {}

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
