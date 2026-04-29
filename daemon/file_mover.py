# daemon/file_mover.py
import shutil
import hashlib
import logging
from pathlib import Path
from dataclasses import dataclass

log = logging.getLogger("ao")

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

    src_folders = {Path(p).parent for p in src_paths}
    for folder in src_folders:
        move_remaining_folder_contents(str(folder), dest_folder)

    delete_empty_source_dirs(src_paths)
    return records


def move_single_file(src_str: str, dest_folder: str) -> MoveRecord:
    src = Path(src_str)
    dest = Path(dest_folder)
    dst = dest / src.name
    log.info("MOVE_FILE src=%r dst=%r src_exists=%s dst_exists=%s", str(src), str(dst), src.exists(), dst.exists())
    if dst.exists():
        raise MoveError(f"Destination already exists: {dst}")
    dest.mkdir(parents=True, exist_ok=True)
    _chmod_dir(dest)
    shutil.move(str(src), str(dst))
    log.info("MOVE_FILE_OK src=%r dst=%r dst_exists=%s", str(src), str(dst), dst.exists())
    try:
        dst.chmod(0o666)
    except Exception:
        pass
    return MoveRecord(src=src_str, dst=str(dst))


def move_remaining_folder_contents(src_folder: str, dest_folder: str):
    src = Path(src_folder)
    dest = Path(dest_folder)
    log.info("SWEEP src=%r exists=%s dest=%r", src_folder, src.exists(), dest_folder)
    if not src.exists() or not src.is_dir():
        log.info("SWEEP_SKIP src missing or not dir")
        return
    items = list(src.iterdir())
    log.info("SWEEP_ITEMS count=%d items=%r", len(items), [i.name for i in items])
    dest.mkdir(parents=True, exist_ok=True)
    for item in items:
        dst = dest / item.name
        if dst.exists():
            log.info("SWEEP_SKIP_EXISTS item=%r", item.name)
            continue
        try:
            shutil.move(str(item), str(dst))
            log.info("SWEEP_MOVED item=%r", item.name)
        except Exception as e:
            log.error("SWEEP_ERROR item=%r error=%r", item.name, str(e))


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
