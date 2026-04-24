import pytest
from pipeline.filename_parser import parse_filename, parse_folder_name

@pytest.mark.parametrize("filename,expected_title,expected_author", [
    ("The Hobbit.mp3", "The Hobbit", None),
    ("01 - The Hobbit.mp3", "The Hobbit", None),
    ("Tolkien, J.R.R. - The Hobbit.mp3", "The Hobbit", "Tolkien, J.R.R."),
    ("The Hobbit [Unabridged].mp3", "The Hobbit", None),
    ("The Hobbit narrated by Andy Serkis.mp3", "The Hobbit", None),
    ("The Hobbit (Lord of the Rings, #0).mp3", "The Hobbit", None),
    ("001_thehobbit_ch01.mp3", "thehobbit", None),
])
def test_parse_filename(filename, expected_title, expected_author):
    title, author = parse_filename(filename)
    assert title.lower() == expected_title.lower()
    if expected_author:
        assert author and expected_author.lower() in author.lower()

def test_parse_folder_name_strips_junk():
    title, author = parse_folder_name("Tolkien - The Hobbit (2001) [MP3]")
    assert "hobbit" in title.lower()
