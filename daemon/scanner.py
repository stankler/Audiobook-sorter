from pathlib import Path
from collections import defaultdict
from models import BookGroup

AUDIO_EXTENSIONS = {".mp3", ".m4b", ".m4a", ".flac", ".ogg", ".opus", ".aac", ".wav"}

def scan_for_books(source_path: str) -> list[BookGroup]:
    root = Path(source_path)
    by_folder: dict[Path, list[Path]] = defaultdict(list)

    for f in root.rglob("*"):
        if f.is_file():
            by_folder[f.parent].append(f)

    groups = []
    for folder, files in sorted(by_folder.items()):
        audio = sorted(f for f in files if f.suffix.lower() in AUDIO_EXTENSIONS)
        if not audio:
            continue
        non_audio = sorted(f for f in files if f.suffix.lower() not in AUDIO_EXTENSIONS)
        groups.append(BookGroup(
            files=[str(f) for f in audio + non_audio],
            folder=str(folder),
        ))
    return groups
