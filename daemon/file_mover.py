# daemon/file_mover.py
import shutil
import hashlib
from pathlib import Path
from dataclasses import dataclass

class MoveError(Exception):
    pass

@dataclass
class MoveRecord:
    src: str
    dst: str

def move_book_files(src_paths: list[str], dest_folder: str) -> list[MoveRecord]:
    dest = Path(dest_folder)
    records = []

    for src_str in src_paths:
        src = Path(src_str)
        dst = dest / src.name
        if dst.exists():
            raise MoveError(f"Destination already exists: {dst}")

    dest.mkdir(parents=True, exist_ok=True)

    for src_str in src_paths:
        src = Path(src_str)
        dst = dest / src.name
        _atomic_move(src, dst)
        records.append(MoveRecord(src=src_str, dst=str(dst)))

    return records

def _atomic_move(src: Path, dst: Path):
    src_hash = _md5(src)
    shutil.copy2(str(src), str(dst))
    if _md5(dst) != src_hash:
        dst.unlink()
        raise MoveError(f"Checksum mismatch after copy: {src}")
    src.unlink()

def _md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

async def undo_moves(records: list[MoveRecord]):
    for r in reversed(records):
        src = Path(r.src)
        dst = Path(r.dst)
        if dst.exists():
            src.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dst), str(src))
