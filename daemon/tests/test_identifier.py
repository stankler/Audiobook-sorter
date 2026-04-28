# daemon/tests/test_identifier.py
import pytest
from unittest.mock import patch, AsyncMock
from models import BookGroup, Config
from identifier import identify_book, _extract_series

HOBBIT_CANDIDATE = {
    "id": "abc",
    "volumeInfo": {
        "title": "The Hobbit",
        "authors": ["J.R.R. Tolkien"],
        "seriesInfo": {"volumeSeries": [{"seriesId": "123", "orderNumber": "1"}]},
    }
}

LOTR_CANDIDATE = {
    "id": "def",
    "volumeInfo": {
        "title": "The Fellowship of the Ring (The Lord of the Rings, Book 1)",
        "authors": ["J.R.R. Tolkien"],
        "seriesInfo": {"volumeSeries": [{"seriesId": "456", "orderNumber": "1"}]},
    }
}


@pytest.mark.asyncio
async def test_identifies_via_tags():
    group = BookGroup(files=["/fake/hobbit.mp3"], folder="/fake")
    cfg = Config(google_books_api_key="key", confidence_threshold=0.85)

    with patch("identifier.read_tags", return_value={"title": "The Hobbit", "author": "J.R.R. Tolkien"}), \
         patch("identifier.query_google_books", AsyncMock(return_value=[HOBBIT_CANDIDATE])), \
         patch("identifier.ol_search_books", AsyncMock(return_value=[])):
        candidates = await identify_book(group, cfg)

    assert len(candidates) > 0
    best = candidates[0]
    assert "hobbit" in best.title.lower()
    assert "TAGS" in best.source.upper()


@pytest.mark.asyncio
async def test_falls_through_to_filename_when_no_tags():
    # Folder name "f" is <=3 chars → skipped by identifier; only filename query fires
    group = BookGroup(files=["/f/Tolkien - The Hobbit.mp3"], folder="/f")
    cfg = Config(google_books_api_key="key", confidence_threshold=0.85)

    with patch("identifier.read_tags", return_value={"title": None, "author": None}), \
         patch("identifier.query_google_books", AsyncMock(return_value=[HOBBIT_CANDIDATE])), \
         patch("identifier.ol_search_books", AsyncMock(return_value=[])):
        candidates = await identify_book(group, cfg)

    assert len(candidates) > 0
    sources = [c.source for c in candidates]
    assert any("FILE" in s.upper() for s in sources)


def test_extract_series_comma_hash():
    name, num = _extract_series("The Name of the Wind (The Kingkiller Chronicle, #1)")
    assert name == "The Kingkiller Chronicle"
    assert num == 1.0


def test_extract_series_book_keyword():
    name, num = _extract_series("The Fellowship of the Ring (The Lord of the Rings, Book 1)")
    assert name == "The Lord of the Rings"
    assert num == 1.0


def test_extract_series_hash_no_comma():
    name, num = _extract_series("Dune (Dune Chronicles #1)")
    assert name == "Dune Chronicles"
    assert num == 1.0


def test_extract_series_none_when_absent():
    name, num = _extract_series("The Hobbit")
    assert name is None
    assert num is None


@pytest.mark.asyncio
async def test_series_extracted_from_title():
    group = BookGroup(files=["/fake/lotr.mp3"], folder="/fake")
    cfg = Config(google_books_api_key="key", confidence_threshold=0.70)

    with patch("identifier.read_tags", return_value={"title": "Fellowship of the Ring", "author": "Tolkien"}), \
         patch("identifier.query_google_books", AsyncMock(return_value=[LOTR_CANDIDATE])), \
         patch("identifier.ol_search_books", AsyncMock(return_value=[])):
        candidates = await identify_book(group, cfg)

    assert len(candidates) > 0
    best = candidates[0]
    assert best.series == "The Lord of the Rings"
    assert best.series_number == 1.0


@pytest.mark.asyncio
async def test_returns_no_high_confidence_when_no_match():
    group = BookGroup(files=["/fake/gibberish_xyz.mp3"], folder="/fake")
    cfg = Config(google_books_api_key="key", confidence_threshold=0.85)

    with patch("identifier.read_tags", return_value={"title": None, "author": None}), \
         patch("identifier.query_google_books", AsyncMock(return_value=[])), \
         patch("identifier.ol_search_books", AsyncMock(return_value=[])):
        candidates = await identify_book(group, cfg)

    assert all(c.confidence == 0.0 for c in candidates)
