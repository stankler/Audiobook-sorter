import pytest
from pathlib import Path
from mutagen.id3 import ID3, TIT2, TPE1
from mutagen.mp4 import MP4
from pipeline.tag_reader import read_tags

def make_tagged_mp3(path: Path, title: str, artist: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tags = ID3()
    tags.add(TIT2(encoding=3, text=title))
    tags.add(TPE1(encoding=3, text=artist))
    tags.save(str(path))

def test_reads_title_and_author(tmp_path):
    f = tmp_path / "book.mp3"
    make_tagged_mp3(f, "The Hobbit", "J.R.R. Tolkien")
    result = read_tags(str(f))
    assert result["title"] == "The Hobbit"
    assert result["author"] == "J.R.R. Tolkien"

def test_missing_tags_returns_none_values(tmp_path):
    f = tmp_path / "untagged.mp3"
    f.write_bytes(b"\x00" * 128)
    result = read_tags(str(f))
    assert result["title"] is None
    assert result["author"] is None

def test_returns_none_on_unreadable_file(tmp_path):
    f = tmp_path / "corrupt.mp3"
    f.write_bytes(b"not audio")
    result = read_tags(str(f))
    assert result["title"] is None
    assert result["author"] is None
