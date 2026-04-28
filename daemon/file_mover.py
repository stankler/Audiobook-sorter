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

    seen_dsts: set[Path] = set()
    for src_str in src_paths:
        src = Path(src_str)
        dst = dest / src.name
        if dst.exists() or dst in seen_dsts:
            raise MoveError(f"Destination already exists: {dst}")
        seen_dsts.add(dst)

    dest.mkdir(parents=True, exist_ok=True)
    _chmod_dir(dest)

    for src_str in src_paths:
        src = Path(src_str)
        dst = dest / src.name
        _atomic_move(src, dst)
        dst.chmod(0o666)
        records.append(MoveRecord(src=src_str, dst=str(dst)))

    delete_empty_source_dirs(src_paths)
    return records


def move_single_file(src_str: str, dest_folder: str) -> MoveRecord:
    src = Path(src_str)
    dest = Path(dest_folder)
    dst = dest / src.name
    if dst.exists():
        raise MoveError(f"Destination already exists: {dst}")
    dest.mkdir(parents=True, exist_ok=True)
    _chmod_dir(dest)
    _atomic_move(src, dst)
    dst.chmod(0o666)
    return MoveRecord(src=src_str, dst=str(dst))


def delete_empty_source_dirs(src_paths: list[str]):
    dirs_to_check: set[Path] = set()
    for p in src_paths:
        dirs_to_check.add(Path(p).parent)
    for d in sorted(dirs_to_check, key=lambda p: len(p.parts), reverse=True):
        _rmdir_if_empty(d)


def _rmdir_if_empty(path: Path):
    try:
        if path.exists() and path.is_dir() and not any(path.iterdir()):
            path.rmdir()
            _rmdir_if_empty(path.parent)
    except Exception:
        pass

def _chmod_dir(path: Path):
    """chmod 777 the directory and all parent dirs up to but not including the dest root."""
    try:
        path.chmod(0o777)
    except Exception:
        pass

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
    errors = []
    for r in reversed(records):
        src = Path(r.src)
        dst = Path(r.dst)
        if dst.exists():
            try:
                src.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(dst), str(src))
            except Exception as e:
                errors.append(f"{dst}: {e}")
    if errors:
        raise MoveError(f"Undo incomplete: {'; '.join(errors)}")
