import pytest
from pathlib import Path
from tests.conftest import make_fake_mp3
from scanner import scan_for_books, AUDIO_EXTENSIONS

def test_single_file_is_one_book(tmp_path):
    make_fake_mp3(tmp_path / "The Hobbit.mp3")
    books = scan_for_books(str(tmp_path))
    assert len(books) == 1
    assert len(books[0].files) == 1

def test_chapter_files_grouped_as_one_book(tmp_path):
    folder = tmp_path / "Way of Kings"
    for i in range(3):
        make_fake_mp3(folder / f"0{i+1} - Way of Kings.mp3")
    books = scan_for_books(str(tmp_path))
    assert len(books) == 1
    assert len(books[0].files) == 3

def test_two_separate_folders_are_two_books(tmp_path):
    make_fake_mp3(tmp_path / "Book A" / "book-a.mp3")
    make_fake_mp3(tmp_path / "Book B" / "book-b.mp3")
    books = scan_for_books(str(tmp_path))
    assert len(books) == 2

def test_non_audio_files_ignored(tmp_path):
    make_fake_mp3(tmp_path / "book.mp3")
    (tmp_path / "cover.jpg").write_bytes(b"fake jpg")
    (tmp_path / "info.txt").write_text("notes")
    books = scan_for_books(str(tmp_path))
    assert len(books) == 1
    assert all(f.endswith(".mp3") for f in books[0].files)

def test_nested_directory_scan(tmp_path):
    make_fake_mp3(tmp_path / "Author" / "Series" / "Book 1" / "01.mp3")
    make_fake_mp3(tmp_path / "Author" / "Series" / "Book 2" / "01.mp3")
    books = scan_for_books(str(tmp_path))
    assert len(books) == 2

def test_files_sorted_within_book(tmp_path):
    folder = tmp_path / "Book"
    make_fake_mp3(folder / "03.mp3")
    make_fake_mp3(folder / "01.mp3")
    make_fake_mp3(folder / "02.mp3")
    books = scan_for_books(str(tmp_path))
    names = [Path(f).name for f in books[0].files]
    assert names == ["01.mp3", "02.mp3", "03.mp3"]
