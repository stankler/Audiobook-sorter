from pathlib import Path
import mutagen
from mutagen.id3 import ID3
from mutagen.mp4 import MP4

def read_tags(file_path: str) -> dict:
    """Returns dict with keys: title, author (both str or None)."""
    result = {"title": None, "author": None}
    try:
        suffix = Path(file_path).suffix.lower()
        if suffix in (".mp3",):
            tags = ID3(file_path)
            title = tags.get("TIT2")
            artist = tags.get("TPE1") or tags.get("TPE2")
            result["title"] = str(title[0]) if title else None
            result["author"] = str(artist[0]) if artist else None
        elif suffix in (".m4b", ".m4a", ".aac"):
            tags = MP4(file_path)
            title = tags.get("\xa9nam")
            artist = tags.get("\xa9ART") or tags.get("aART")
            result["title"] = title[0] if title else None
            result["author"] = artist[0] if artist else None
        else:
            audio = mutagen.File(file_path)
            if audio and hasattr(audio, "tags") and audio.tags:
                result["title"] = audio.tags.get("title", [None])[0]
                result["author"] = audio.tags.get("artist", [None])[0]
    except Exception:
        pass
    return result
