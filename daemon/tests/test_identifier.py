# daemon/tests/test_identifier.py
import pytest
from unittest.mock import patch, AsyncMock
from models import BookGroup, IdentificationSource, Config, STTEngine
from identifier import identify_book

HOBBIT_CANDIDATE = {
    "id": "abc",
    "volumeInfo": {
        "title": "The Hobbit",
        "authors": ["J.R.R. Tolkien"],
        "seriesInfo": {"bookSeries": [{"seriesId": "xyz", "orderNumber": "0"}]},
    }
}

@pytest.mark.asyncio
async def test_identifies_via_tags():
    group = BookGroup(files=["/fake/hobbit.mp3"], folder="/fake")
    cfg = Config(google_books_api_key="key", confidence_threshold=0.85)

    with patch("identifier.read_tags", return_value={"title": "The Hobbit", "author": "J.R.R. Tolkien"}), \
         patch("identifier.query_google_books", AsyncMock(return_value=[HOBBIT_CANDIDATE])):
        match = await identify_book(group, cfg)

    assert match is not None
    assert match.source == IdentificationSource.TAGS
    assert "hobbit" in match.title.lower()

@pytest.mark.asyncio
async def test_falls_through_to_filename_when_no_tags():
    group = BookGroup(files=["/fake/Tolkien - The Hobbit.mp3"], folder="/fake")
    cfg = Config(google_books_api_key="key", confidence_threshold=0.85)

    with patch("identifier.read_tags", return_value={"title": None, "author": None}), \
         patch("identifier.query_google_books", AsyncMock(return_value=[HOBBIT_CANDIDATE])):
        match = await identify_book(group, cfg)

    assert match is not None
    assert match.source == IdentificationSource.FILENAME

@pytest.mark.asyncio
async def test_returns_none_when_no_match_found():
    group = BookGroup(files=["/fake/gibberish_xyz.mp3"], folder="/fake")
    cfg = Config(google_books_api_key="key", confidence_threshold=0.85)

    with patch("identifier.read_tags", return_value={"title": None, "author": None}), \
         patch("identifier.query_google_books", AsyncMock(return_value=[])):
        match = await identify_book(group, cfg)

    assert match is None
