import re
from difflib import SequenceMatcher


def _normalize_title(t: str) -> str:
    t = re.sub(r'\s*\([^)]*(?:#|[Bb]ook)\s*\d+[^)]*\)', '', t)
    t = re.sub(r'^(?:the|a|an)\s+', '', t.strip(), flags=re.IGNORECASE)
    return t.lower().strip()


def score_candidate(query_title: str, query_author: str | None, candidate: dict) -> float:
    """
    Score a candidate book from Google Books against query title and author.

    Args:
        query_title: The title being searched for
        query_author: The author being searched for (optional)
        candidate: A candidate book dict with volumeInfo

    Returns:
        A score between 0.0 and 1.0 (65% title weight, 35% author weight)
    """
    info = candidate.get("volumeInfo", {})
    book_title = info.get("title", "")
    book_authors = info.get("authors", [])

    title_sim = SequenceMatcher(
        None, _normalize_title(query_title), _normalize_title(book_title)
    ).ratio()

    if book_authors and query_author:
        author_sim = max(
            SequenceMatcher(None, query_author.lower(), a.lower()).ratio()
            for a in book_authors
        )
        # Penalize weak author matches — if similarity < 0.5, treat as mismatch
        if author_sim < 0.5:
            author_sim = 0.0
    elif not query_author:
        author_sim = 0.5  # neutral — no author to compare
    else:
        author_sim = 0.0

    return round(title_sim * 0.65 + author_sim * 0.35, 4)


def best_candidate(
    query_title: str, query_author: str | None, candidates: list[dict], threshold: float
) -> tuple[dict | None, float]:
    """
    Find the best matching candidate from a list of candidates.

    Args:
        query_title: The title being searched for
        query_author: The author being searched for (optional)
        candidates: A list of candidate book dicts from Google Books
        threshold: Minimum score to return a match

    Returns:
        A tuple of (best_candidate_or_None, score). Returns (None, score) if
        no candidate exceeds threshold.
    """
    if not candidates:
        return None, 0.0
    scored = [(c, score_candidate(query_title, query_author, c)) for c in candidates]
    best, score = max(scored, key=lambda x: x[1])
    if score >= threshold:
        return best, score
    return None, score
