# daemon/identifier.py
from models import BookGroup, BookMatch, IdentificationSource, Config, STTEngine
from pipeline.tag_reader import read_tags
from pipeline.filename_parser import parse_filename, parse_folder_name
from pipeline.google_books import query_google_books
from pipeline.stt_engine import transcribe_book, extract_title_from_transcript
from confidence import best_candidate
from pathlib import Path

async def identify_book(group: BookGroup, cfg: Config) -> BookMatch | None:
    if not group.files:
        return None
    first_file = group.files[0]
    threshold = cfg.confidence_threshold

    # Stage 1: ID3 tags
    tags = read_tags(first_file)
    if tags["title"]:
        candidates = await query_google_books(tags["title"], tags["author"], cfg.google_books_api_key)
        best, score = best_candidate(tags["title"], tags["author"], candidates, threshold)
        if best:
            return _make_match(best, score, IdentificationSource.TAGS)

    # Stage 2: Filename parsing
    fname_title, fname_author = parse_filename(Path(first_file).name)
    if not fname_title:
        folder_title, folder_author = parse_folder_name(Path(group.folder).name)
        fname_title, fname_author = folder_title, folder_author

    if fname_title and len(fname_title) > 3:
        candidates = await query_google_books(fname_title, fname_author, cfg.google_books_api_key)
        best, score = best_candidate(fname_title, fname_author, candidates, threshold)
        if best:
            return _make_match(best, score, IdentificationSource.FILENAME)

    # Stage 3: STT
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
                    return _make_match(best, score, IdentificationSource.STT)

    return None

def _make_match(candidate: dict, score: float, source: IdentificationSource) -> BookMatch:
    info = candidate.get("volumeInfo", {})
    authors = info.get("authors", [])
    author = authors[0] if authors else "Unknown"

    series = None
    series_number = None
    series_info = info.get("seriesInfo", {})
    if series_info and series_info.get("bookSeries"):
        first_series = series_info["bookSeries"][0]
        series_raw = first_series.get("seriesId", "")
        series = series_raw if series_raw and not series_raw.isdigit() else None
        try:
            series_number = float(first_series.get("orderNumber", ""))
        except (ValueError, TypeError):
            pass

    return BookMatch(
        title=info.get("title", "Unknown"),
        author=author,
        series=series,
        series_number=series_number,
        google_books_id=candidate.get("id"),
        confidence=score,
        source=source,
    )
