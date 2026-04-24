# daemon/tests/test_tag_writer.py
from pathlib import Path
from mutagen.id3 import ID3, TIT2, TPE1
from models import BookMatch, IdentificationSource
from tag_writer import write_tags_to_files

def make_tagged_mp3(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    tags = ID3()
    tags.add(TIT2(encoding=3, text="Old Title"))
    tags.add(TPE1(encoding=3, text="Old Author"))
    tags.save(str(path))

def test_writes_title_and_author(tmp_path):
    f = tmp_path / "book.mp3"
    make_tagged_mp3(f)
    match = BookMatch(title="The Hobbit", author="J.R.R. Tolkien",
                      confidence=0.95, source=IdentificationSource.TAGS)
    write_tags_to_files([str(f)], match)
    tags = ID3(str(f))
    assert str(tags["TIT2"]) == "The Hobbit"
    assert str(tags["TPE1"]) == "J.R.R. Tolkien"

def test_skips_unreadable_file(tmp_path):
    f = tmp_path / "corrupt.mp3"
    f.write_bytes(b"not audio")
    match = BookMatch(title="Test", author="Author",
                      confidence=0.95, source=IdentificationSource.TAGS)
    write_tags_to_files([str(f)], match)
    assert f.read_bytes() == b"not audio"
