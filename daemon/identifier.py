import logging
import re
from pathlib import Path
from models import BookGroup, Candidate, Config
from pipeline.tag_reader import read_tags
from pipeline.filename_parser import parse_filename, parse_folder_name
from pipeline.google_books import query_google_books
from pipeline.open_library import search_books as ol_search_books
from confidence import score_candidate
from pipeline.claude_identifier import find_series as claude_find_series

logger = logging.getLogger("ao")


async def identify_book(group: BookGroup, cfg: Config) -> list[Candidate]:
    if not group.files:
        return []
    first_file = group.files[0]

    # Step 1: ID3 tags
    tags = read_tags(first_file)
    tag_title: str | None = None
    tag_author: str | None = None
    tag_series: str | None = None
    tag_series_num: float | None = None
    if tags.get("title"):
        tag_title, tag_series, tag_series_num = _clean_tag_title(tags["title"])
        tag_author = tags.get("author") or None
    logger.info("TAGS     folder=%r  title=%r  author=%r", group.folder, tag_title, tag_author)

    # Step 2: Folder name
    path_author = _author_from_path(group.folder, cfg.source_path)
    folder_title, folder_author = parse_folder_name(Path(group.folder).name)
    if path_author:
        folder_author = path_author
    logger.info("FOLDER   folder=%r  title=%r  author=%r", group.folder, folder_title, folder_author)

    # Step 3: Filename
    fname_title, fname_author = parse_filename(Path(first_file).name)
    if path_author:
        fname_author = path_author
    logger.info("FILENAME folder=%r  title=%r  author=%r", group.folder, fname_title, fname_author)

    candidates: list[Candidate] = []

    async def _query(title: str | None, author: str | None, source_gb: str, source_ol: str,
                     fallback_series: str | None = None, fallback_series_num: float | None = None,
                     skip_if: set[str] | None = None):
        if not title or len(title) <= 3:
            return
        if skip_if and title in skip_if:
            return
        raw = await query_google_books(title, author, cfg.google_books_api_key)
        logger.info("%s  title=%r → %d results", source_gb, title, len(raw))
        for item in raw[:5]:
            candidates.append(_gb_candidate(item, source_gb, title, author, fallback_series, fallback_series_num))
        raw = await ol_search_books(title, author)
        logger.info("%s  title=%r → %d results", source_ol, title, len(raw))
        for item in raw[:5]:
            candidates.append(_ol_candidate(item, source_ol, fallback_series, fallback_series_num))

    # Step 4: Query Google Books + Open Library with each source
    await _query(tag_title, tag_author, "GB_TAGS ", "OL_TAGS ",
                 fallback_series=tag_series, fallback_series_num=tag_series_num)
    await _query(folder_title, folder_author, "GB_FOLD ", "OL_FOLD ",
                 skip_if={tag_title} if tag_title else None)
    await _query(fname_title, fname_author, "GB_FILE ", "OL_FILE ",
                 skip_if={tag_title, folder_title} - {None})

    # Step 5: Claude series lookup
    if cfg.anthropic_api_key:
        best = next((c for c in candidates if c.confidence > 0), None)
        cl_title = (best.title if best else None) or tag_title or folder_title or fname_title
        cl_author = (best.author if best else None) or tag_author or folder_author or fname_author
        if cl_title and cl_author:
            cl_series, cl_series_num = await claude_find_series(cl_title, cl_author, cfg.anthropic_api_key)
            if cl_series:
                candidates.append(Candidate(
                    title=cl_title, author=cl_author,
                    series=cl_series, series_number=cl_series_num,
                    source="Claude", confidence=0.85,
                ))

    # Add locally-parsed values as candidates so they surface in UI datalists
    for title, author, source in [
        (tag_title,    tag_author,    "Tags (parsed)"),
        (folder_title, folder_author, "Folder (parsed)"),
        (fname_title,  fname_author,  "Filename (parsed)"),
    ]:
        if title and len(title) > 3:
            candidates.append(Candidate(
                title=title, author=author or "Unknown",
                series=tag_series if source == "Tags (parsed)" else None,
                series_number=tag_series_num if source == "Tags (parsed)" else None,
                source=source, confidence=0.0,
            ))

    # Deduplicate by title+author, but always keep Claude candidates so they
    # appear in the UI. For non-Claude dupes: copy series onto survivor if missing.
    seen: dict[tuple[str, str], int] = {}
    deduped: list[Candidate] = []
    for c in candidates:
        key = (c.title.lower().strip(), c.author.lower().strip())
        if key in seen and c.source != "Claude":
            existing = deduped[seen[key]]
            if c.series and not existing.series:
                deduped[seen[key]] = existing.model_copy(update={
                    "series": c.series,
                    "series_number": c.series_number if existing.series_number is None else existing.series_number,
                })
        else:
            seen[key] = len(deduped)
            deduped.append(c)
    deduped.sort(key=lambda c: c.confidence, reverse=True)

    logger.info("CANDIDATES folder=%r  total=%d", group.folder, len(deduped))
    return deduped


def _gb_candidate(raw: dict, source: str, query_title: str, query_author: str | None,
                  fallback_series: str | None, fallback_series_num: float | None) -> Candidate:
    info = raw.get("volumeInfo", {})
    authors = info.get("authors", [])
    title = info.get("title", "Unknown")
    author = authors[0] if authors else "Unknown"

    series: str | None = None
    series_number: float | None = None

    vol_series = (info.get("seriesInfo") or {}).get("volumeSeries", [])
    if vol_series:
        try:
            series_number = float(vol_series[0].get("orderNumber", ""))
        except (ValueError, TypeError):
            pass

    for field in (title, info.get("subtitle", "")):
        name, num = _extract_series(field)
        if name:
            series = name
            if series_number is None and num is not None:
                series_number = num
            break

    if series is None and fallback_series:
        series = fallback_series
        if series_number is None:
            series_number = fallback_series_num

    return Candidate(
        title=title, author=author, series=series, series_number=series_number,
        source=source, confidence=score_candidate(query_title, query_author, raw),
    )


def _ol_candidate(raw: dict, source: str, fallback_series: str | None, fallback_series_num: float | None) -> Candidate:
    series = raw.get("series") or fallback_series
    series_number = raw.get("series_number")
    if series_number is None and series == fallback_series:
        series_number = fallback_series_num
    return Candidate(
        title=raw.get("title", "Unknown"),
        author=raw.get("author", "Unknown"),
        series=series,
        series_number=series_number,
        source=source,
        confidence=0.75,
    )


def _clean_tag_title(title: str) -> tuple[str, str | None, float | None]:
    series: str | None = None
    series_num: float | None = None

    title = re.sub(r'^\.{2,}\s*', '', title).strip()
    # Strip audiobook quality markers: (Unabridged), [Unabridged], ", Unabridged"
    title = re.sub(r',?\s*[\(\[](?:Un)?abridged[\)\]]', '', title, flags=re.IGNORECASE).strip()
    title = re.sub(r',?\s*(?:Un)?abridged$', '', title, flags=re.IGNORECASE).strip()

    # Pattern 1: "Series #N: Title" or "Series #N - Title"
    m = re.match(r'^(.+?)\s*#(\d+(?:\.\d+)?)\s*[:\-]\s*(.+)$', title)
    if m:
        series, series_num, clean = m.group(1).strip(), float(m.group(2)), m.group(3).strip()
        clean = re.sub(r'\s*\([^)]*(?:Book\s*\d|#\d)[^)]*\)', '', clean).strip()
        return clean, series, series_num

    # Pattern 2: "Title: Series, Book N" or "Title: Series, Volume N"
    m = re.match(r'^(.+):\s*([^:]+?),?\s*(?:[Bb]ook|[Vv]olume|[Vv]ol\.?)\s*(\d+(?:\.\d+)?)\s*$', title)
    if m:
        clean, series_raw, series_num = m.group(1).strip(), m.group(2).strip(), float(m.group(3))
        if '(' in series_raw:
            series_raw = series_raw.rsplit('(', 1)[1].strip()
        return clean, series_raw, series_num

    clean = re.sub(r'\s*\([^)]*(?:Book\s*\d|#\d)[^)]*\)', '', title).strip()
    clean = re.sub(r'[\s\-]*0\d{1,2}$', '', clean).strip()
    return clean or title, series, series_num


def _author_from_path(folder: str, source_path: str) -> str | None:
    try:
        parts = Path(folder).relative_to(source_path).parts
    except ValueError:
        return None
    if len(parts) >= 2 and parts[0] and not re.match(r'^#?\d', parts[0]):
        return parts[0]
    return None


def _extract_series(text: str) -> tuple[str | None, float | None]:
    m = re.search(r'\(([^)]+),\s*(?:#|[Bb]ook\s*)(\d+(?:\.\d+)?)\)', text)
    if m:
        return m.group(1).strip(), float(m.group(2))
    m = re.search(r'\(([^)#,]+)\s*#(\d+(?:\.\d+)?)\)', text)
    if m:
        return m.group(1).strip(), float(m.group(2))
    return None, None
