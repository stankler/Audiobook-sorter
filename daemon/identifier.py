# daemon/identifier.py
import logging
import re
from pathlib import Path
from models import BookGroup, BookMatch, IdentificationSource, Config, STTEngine
from pipeline.tag_reader import read_tags
from pipeline.filename_parser import parse_filename, parse_folder_name
from pipeline.google_books import query_google_books
from pipeline.stt_engine import transcribe_book, extract_title_from_transcript
from pipeline.open_library import lookup_series
from pipeline.claude_identifier import identify_with_claude
from confidence import best_candidate

logger = logging.getLogger("ao")

async def identify_book(group: BookGroup, cfg: Config) -> BookMatch | None:
    if not group.files:
        return None
    first_file = group.files[0]
    threshold = cfg.confidence_threshold

    # Stage 1: Claude API
    if cfg.anthropic_api_key:
        claude_result = await identify_with_claude(
            group.folder, group.files, cfg.source_path, cfg.anthropic_api_key, cfg.google_books_api_key
        )
        if claude_result:
            candidates = await query_google_books(
                claude_result["title"], claude_result["author"], cfg.google_books_api_key
            )
            best, score = best_candidate(
                claude_result["title"], claude_result["author"], candidates, threshold
            )
            logger.info("STAGE1_CLAUDE candidates=%d best_score=%.2f", len(candidates), score)
            if best:
                match = await _fill_series(
                    _make_match(best, score, IdentificationSource.CLAUDE), group, cfg
                )
                if match.series is None and claude_result.get("series"):
                    match = match.model_copy(update={
                        "series": claude_result["series"],
                        "series_number": claude_result.get("series_number"),
                    })
                return match
            # Claude found metadata but Google Books has no entry — trust Claude directly
            if claude_result["title"] and claude_result["author"]:
                logger.info("STAGE1_CLAUDE_DIRECT no GB match, using Claude result directly")
                return BookMatch(
                    title=claude_result["title"],
                    author=claude_result["author"],
                    series=claude_result.get("series"),
                    series_number=claude_result.get("series_number"),
                    confidence=0.75,
                    source=IdentificationSource.CLAUDE,
                )

    # Stage 2: ID3 tags
    tags = read_tags(first_file)
    logger.info("STAGE2 folder=%r tags_title=%r tags_author=%r", group.folder, tags.get("title"), tags.get("author"))
    if tags["title"]:
        clean_title, tag_series, tag_series_num = _clean_tag_title(tags["title"])
        candidates = await query_google_books(clean_title, tags["author"], cfg.google_books_api_key)
        best, score = best_candidate(clean_title, tags["author"], candidates, threshold)
        logger.info("STAGE2_RESULT clean_title=%r candidates=%d best_score=%.2f", clean_title, len(candidates), score)
        if best:
            match = await _fill_series(_make_match(best, score, IdentificationSource.TAGS), group, cfg)
            if match.series is None and tag_series:
                match = match.model_copy(update={"series": tag_series, "series_number": tag_series_num})
            return match

    # Stage 3: Filename parsing
    path_author = _author_from_path(group.folder, cfg.source_path)

    fname_title, fname_author = parse_filename(Path(first_file).name)
    if not fname_title:
        folder_title, folder_author = parse_folder_name(Path(group.folder).name)
        fname_title, fname_author = folder_title, folder_author

    if not fname_author:
        fname_author = path_author

    logger.info("STAGE3 folder=%r query_title=%r query_author=%r", group.folder, fname_title, fname_author)
    if fname_title and len(fname_title) > 3:
        candidates = await query_google_books(fname_title, fname_author, cfg.google_books_api_key)
        best, score = best_candidate(fname_title, fname_author, candidates, threshold)
        logger.info("STAGE3_RESULT candidates=%d best_score=%.2f", len(candidates), score)
        if best:
            return await _fill_series(_make_match(best, score, IdentificationSource.FILENAME), group, cfg)

    # Stage 4: STT
    if cfg.stt_engine != STTEngine.NONE:
        transcript = await transcribe_book(
            first_file, cfg.stt_engine, cfg.whisper_model, cfg.stt_api_key
        )
        if transcript:
            stt_title, stt_author = extract_title_from_transcript(transcript)
            if stt_title:
                candidates = await query_google_books(stt_title, stt_author, cfg.google_books_api_key)
                best, score = best_candidate(stt_title, stt_author, candidates, threshold)
                if best:
                    return await _fill_series(_make_match(best, score, IdentificationSource.STT), group, cfg)

    return None


async def _fill_series(match: BookMatch, group: BookGroup, cfg: Config) -> BookMatch:
    if match.series is not None:
        return match

    # Folder structure first (fast, no network)
    series, series_number = _infer_series_from_path(group.folder, cfg.source_path)
    if series:
        logger.info("SERIES_FOLDER folder=%r → series=%r series_number=%r", group.folder, series, series_number)
        return match.model_copy(update={
            "series": series,
            "series_number": series_number if match.series_number is None else match.series_number,
        })

    # Open Library fallback
    series = await lookup_series(match.title, match.author)
    if series:
        logger.info("SERIES_OL title=%r → series=%r", match.title, series)
        return match.model_copy(update={"series": series})

    return match

def _clean_tag_title(title: str) -> tuple[str, str | None, float | None]:
    """Return (clean_title_for_query, series_or_None, series_number_or_None).

    Handles common audiobook tag formats:
      "The Dresden Files #2: Fool Moon"       → ("Fool Moon", "The Dresden Files", 2.0)
      "Peace Talks: Dresden Files, Book 16"   → ("Peace Talks", "Dresden Files", 16.0)
      "The Law: A Dresden Files Novella (...)"→ ("The Law", ...)
    """
    series: str | None = None
    series_num: float | None = None

    # Pattern 1: "Series #N: Title" or "Series #N - Title"
    m = re.match(r'^(.+?)\s*#(\d+(?:\.\d+)?)\s*[:\-]\s*(.+)$', title)
    if m:
        series, series_num, clean = m.group(1).strip(), float(m.group(2)), m.group(3).strip()
        clean = re.sub(r'\s*\([^)]*(?:Book\s*\d|#\d)[^)]*\)', '', clean).strip()
        return clean, series, series_num

    # Pattern 2: "Title: Series, Book N" or "Title: Subtitle: Series, Book N"
    # Greedy (.+) for title so "Dire: Time: The Dire Saga, Book 3" → title="Dire: Time", series="The Dire Saga"
    m = re.match(r'^(.+):\s*([^:]+?),?\s*[Bb]ook\s*(\d+(?:\.\d+)?)\s*$', title)
    if m:
        clean, series_raw, series_num = m.group(1).strip(), m.group(2).strip(), float(m.group(3))
        # If series_raw captured extra preamble like "A X Novella (Series", take part after last "("
        if '(' in series_raw:
            series_raw = series_raw.rsplit('(', 1)[1].strip()
        return clean, series_raw, series_num

    # Strip parenthetical series info but keep the title clean
    clean = re.sub(r'\s*\([^)]*(?:Book\s*\d|#\d)[^)]*\)', '', title).strip()
    return clean or title, series, series_num


def _author_from_path(folder: str, source_path: str) -> str | None:
    try:
        parts = Path(folder).relative_to(source_path).parts
    except ValueError:
        return None
    # parts[0] is author only when there are multiple components and it doesn't
    # look like a series/book folder (e.g. "#8 Proven Guilty")
    if len(parts) >= 2 and parts[0] and not re.match(r'^#?\d', parts[0]):
        return parts[0]
    return None


def _infer_series_from_path(folder: str, source_path: str) -> tuple[str | None, float | None]:
    try:
        parts = Path(folder).relative_to(source_path).parts
    except ValueError:
        parts = Path(folder).parts
    # Leaf folder "Series Name #N Book Title"
    if parts:
        m = re.match(r'^(.+?)\s+#(\d+(?:\.\d+)?)\s+', parts[-1])
        if m:
            return m.group(1).strip(), float(m.group(2))
    # Parent folder is series when structure is Author/Series/Book
    if len(parts) >= 3:
        return parts[-2], None
    return None, None


def _extract_series_from_title(text: str) -> tuple[str | None, float | None]:
    import re
    # "(Series Name, #N)" or "(Series Name, Book N)"
    m = re.search(r'\(([^)]+),\s*(?:#|[Bb]ook\s*)(\d+(?:\.\d+)?)\)', text)
    if m:
        return m.group(1).strip(), float(m.group(2))
    # "(Series Name #N)"
    m = re.search(r'\(([^)#,]+)\s*#(\d+(?:\.\d+)?)\)', text)
    if m:
        return m.group(1).strip(), float(m.group(2))
    return None, None

def _make_match(candidate: dict, score: float, source: IdentificationSource) -> BookMatch:
    info = candidate.get("volumeInfo", {})
    authors = info.get("authors", [])
    author = authors[0] if authors else "Unknown"

    series = None
    series_number = None

    # Get order number from volumeSeries (seriesId is an opaque ID, not a name)
    series_info = info.get("seriesInfo", {})
    vol_series = series_info.get("volumeSeries", []) if series_info else []
    if vol_series:
        try:
            series_number = float(vol_series[0].get("orderNumber", ""))
        except (ValueError, TypeError):
            pass

    # Series name is embedded in the title/subtitle by Google Books
    raw_title = info.get("title", "")
    raw_subtitle = info.get("subtitle", "")
    for field in (raw_title, raw_subtitle):
        name, num = _extract_series_from_title(field)
        if name:
            series = name
            if series_number is None and num is not None:
                series_number = num
            break

    logger.info(
        "SERIES_PARSE title=%r subtitle=%r → series=%r series_number=%r",
        raw_title, raw_subtitle, series, series_number,
    )

    return BookMatch(
        title=info.get("title", "Unknown"),
        author=author,
        series=series,
        series_number=series_number,
        google_books_id=candidate.get("id"),
        confidence=score,
        source=source,
    )
