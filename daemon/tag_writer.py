# daemon/tag_writer.py
from pathlib import Path
from models import BookMatch

def write_tags_to_files(file_paths: list[str], match: BookMatch):
    for path_str in file_paths:
        try:
            _write_tags(path_str, match)
        except Exception:
            pass

def _write_tags(path_str: str, match: BookMatch):
    from mutagen.id3 import ID3, TIT2, TPE1, TALB, ID3NoHeaderError
    from mutagen.mp4 import MP4

    suffix = Path(path_str).suffix.lower()
    if suffix == ".mp3":
        try:
            tags = ID3(path_str)
        except ID3NoHeaderError:
            tags = ID3()
        tags.setall("TIT2", [TIT2(encoding=3, text=match.title)])
        tags.setall("TPE1", [TPE1(encoding=3, text=match.author)])
        if match.series:
            tags.setall("TALB", [TALB(encoding=3, text=match.series)])
        tags.save(path_str)
    elif suffix in (".m4b", ".m4a"):
        audio = MP4(path_str)
        audio["\xa9nam"] = [match.title]
        audio["\xa9ART"] = [match.author]
        if match.series:
            audio["\xa9alb"] = [match.series]
        audio.save()
