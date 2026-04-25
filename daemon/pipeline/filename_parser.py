import re
from pathlib import Path


def parse_filename(filename: str) -> tuple[str, str | None]:
    """Returns (title_candidate, author_candidate_or_None)."""
    name = Path(filename).stem
    return _parse_name(name)


def parse_folder_name(folder_name: str) -> tuple[str, str | None]:
    return _parse_name(folder_name)


def _parse_name(name: str) -> tuple[str, str | None]:
    # Strip leading track numbers: "01 - ", "001_", "1. " or "#10 "
    name = re.sub(r"^#?\d+[\s\-_\.]+", "", name)
    # Strip trailing chapter/part indicators: "_ch01", "_chapter01", "_part01", etc.
    name = re.sub(r"[_\-](?:ch|chapter|part|track|pt)\w*$", "", name, flags=re.IGNORECASE)
    # Strip bracketed content: [Unabridged], [MP3], (2001)
    name = re.sub(r"\[.*?\]", "", name)
    name = re.sub(r"\(\d{4}\)", "", name)
    # Strip series info: (Series Name, #N) or (Series Book N)
    name = re.sub(r"\s*\([^)]*[#,]\s*\d+[^)]*\)", "", name)
    name = re.sub(r"\s*\([^)]*[Bb]ook\s+\d+[^)]*\)", "", name)
    # Strip narrator credit
    name = re.sub(r"\s*(narrated|read)\s+by\s+.*", "", name, flags=re.IGNORECASE)
    # Check for "Author - Title" or "Last, First - Title" pattern
    parts = re.split(r"\s+-\s+", name.strip())
    if len(parts) == 2:
        first, second = parts[0].strip(), parts[1].strip()
        # Heuristic: if first part looks like an author (has comma or "Last, First" form)
        if "," in first or re.match(r"^[A-Z][a-z]+,?\s+[A-Z]", first):
            return second, first
        return second, first  # Return both; caller decides
    return name.strip(), None
