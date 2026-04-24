# daemon/path_builder.py
import re
from models import BookMatch

def build_proposed_path(match: BookMatch, dest_root: str) -> str:
    author = _sanitize(match.author)
    title = _sanitize(match.title)

    if match.series and match.series_number is not None:
        num = int(match.series_number) if match.series_number == int(match.series_number) else match.series_number
        series = _sanitize(match.series)
        book_folder = f"{num} - {title}"
        return f"{dest_root}/{author}/{series}/{book_folder}"

    return f"{dest_root}/{author}/{title}"

def _sanitize(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name
