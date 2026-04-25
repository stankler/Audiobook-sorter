# daemon/tests/test_identifier.py
import pytest
from unittest.mock import patch, AsyncMock
from models import BookGroup, IdentificationSource, Config, STTEngine
from identifier import identify_book, _extract_series_from_title, _infer_series_from_path

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

def test_extract_series_comma_hash():
    name, num = _extract_series_from_title("The Name of the Wind (The Kingkiller Chronicle, #1)")
    assert name == "The Kingkiller Chronicle"
    assert num == 1.0

def test_extract_series_book_keyword():
    name, num = _extract_series_from_title("The Fellowship of the Ring (The Lord of the Rings, Book 1)")
    assert name == "The Lord of the Rings"
    assert num == 1.0

def test_extract_series_hash_no_comma():
    name, num = _extract_series_from_title("Dune (Dune Chronicles #1)")
    assert name == "Dune Chronicles"
    assert num == 1.0

def test_extract_series_none_when_absent():
    name, num = _extract_series_from_title("The Hobbit")
    assert name is None
    assert num is None

def test_infer_series_from_leaf_hash_pattern():
    series, num = _infer_series_from_path(
        "/audiobooks/Alastair Reynolds/Revelation Space/Revelation Space #1 Revelation Space",
        "/audiobooks"
    )
    assert series == "Revelation Space"
    assert num == 1.0

def test_infer_series_from_parent_folder():
    series, num = _infer_series_from_path(
        "/audiobooks/Alastair Reynolds/Poseidon's Children/Blue Remembered Earth",
        "/audiobooks"
    )
    assert series == "Poseidon's Children"
    assert num is None

def test_infer_series_standalone_book():
    series, num = _infer_series_from_path(
        "/audiobooks/Alastair Reynolds/Century Rain",
        "/audiobooks"
    )
    assert series is None

def test_infer_series_fractional_number():
    series, num = _infer_series_from_path(
        "/audiobooks/Alastair Reynolds/Revelation Space/Revelation Space #0.1 The Prefect",
        "/audiobooks"
    )
    assert series == "Revelation Space"
    assert num == 0.1

@pytest.mark.asyncio
async def test_series_extracted_from_title():
    group = BookGroup(files=["/fake/lotr.mp3"], folder="/fake")
    cfg = Config(google_books_api_key="key", confidence_threshold=0.70)

    with patch("identifier.read_tags", return_value={"title": "Fellowship of the Ring", "author": "Tolkien"}), \
         patch("identifier.query_google_books", AsyncMock(return_value=[LOTR_CANDIDATE])):
        match = await identify_book(group, cfg)

    assert match is not None
    assert match.series == "The Lord of the Rings"
    assert match.series_number == 1.0

@pytest.mark.asyncio
async def test_returns_none_when_no_match_found():
    group = BookGroup(files=["/fake/gibberish_xyz.mp3"], folder="/fake")
    cfg = Config(google_books_api_key="key", confidence_threshold=0.85)

    with patch("identifier.read_tags", return_value={"title": None, "author": None}), \
         patch("identifier.query_google_books", AsyncMock(return_value=[])):
        match = await identify_book(group, cfg)

    assert match is None
