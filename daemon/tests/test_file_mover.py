# daemon/tests/test_file_mover.py
import pytest
from pathlib import Path
from tests.conftest import make_fake_mp3
from file_mover import move_book_files, undo_moves, MoveError

def test_moves_single_file(tmp_path):
    src = make_fake_mp3(tmp_path / "src" / "book.mp3")
    dest = tmp_path / "dest" / "Author" / "Book"
    moves = move_book_files([str(src)], str(dest))
    assert (dest / "book.mp3").exists()
    assert not src.exists()
    assert len(moves) == 1

def test_preserves_original_filename(tmp_path):
    src = make_fake_mp3(tmp_path / "src" / "01 - ch01.mp3")
    dest = tmp_path / "dest" / "Author" / "Book"
    move_book_files([str(src)], str(dest))
    assert (dest / "01 - ch01.mp3").exists()

def test_raises_on_destination_conflict(tmp_path):
    src = make_fake_mp3(tmp_path / "src" / "book.mp3")
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "book.mp3").write_bytes(b"existing")
    with pytest.raises(MoveError, match="already exists"):
        move_book_files([str(src)], str(dest))

def test_creates_destination_directory(tmp_path):
    src = make_fake_mp3(tmp_path / "src" / "book.mp3")
    dest = tmp_path / "deep" / "nested" / "path"
    move_book_files([str(src)], str(dest))
    assert dest.exists()

def test_raises_on_intra_batch_duplicate(tmp_path):
    src1 = make_fake_mp3(tmp_path / "a" / "book.mp3")
    src2 = make_fake_mp3(tmp_path / "b" / "book.mp3")
    dest = tmp_path / "dest"
    with pytest.raises(MoveError, match="already exists"):
        move_book_files([str(src1), str(src2)], str(dest))

@pytest.mark.asyncio
async def test_undo_moves_file_back(tmp_path):
    src = make_fake_mp3(tmp_path / "src" / "book.mp3")
    dest = tmp_path / "dest"
    moves = move_book_files([str(src)], str(dest))
    await undo_moves(moves)
    assert src.exists()
    assert not (dest / "book.mp3").exists()
