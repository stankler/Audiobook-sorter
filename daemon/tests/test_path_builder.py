# daemon/tests/test_path_builder.py
from path_builder import build_proposed_path
from models import BookMatch, IdentificationSource

def match(title, author, series=None, series_number=None):
    return BookMatch(
        title=title, author=author, series=series, series_number=series_number,
        confidence=0.95, source=IdentificationSource.TAGS
    )

def test_standalone_book_path():
    path = build_proposed_path(match("The Shining", "King, Stephen"), "/library")
    assert path == "/library/King, Stephen/The Shining"

def test_series_book_path():
    path = build_proposed_path(
        match("The Way of Kings", "Sanderson, Brandon", "Stormlight Archive", 1.0),
        "/library"
    )
    assert path == "/library/Sanderson, Brandon/Stormlight Archive/1 - The Way of Kings"

def test_sanitizes_special_chars():
    path = build_proposed_path(match("Book: A Story", "O'Brien, Tim"), "/library")
    assert ":" not in path

def test_fractional_series_number():
    path = build_proposed_path(
        match("A Hobbit's Tale", "Tolkien, J.R.R.", "Middle Earth", 0.5),
        "/library"
    )
    assert "0.5" in path
