# Audiobook Organizer Unraid Plugin — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a native Unraid plugin that scans a chaotic audiobook directory, identifies books via a 4-stage pipeline (metadata tags → filename parsing → Google Books API → speech-to-text), proposes an organized folder structure, and moves files only after per-book user approval in the Unraid web UI.

**Architecture:** Python FastAPI daemon handles all heavy lifting (scanning, identification, file moves, SQLite state). PHP/vanilla-JS Unraid plugin page communicates with the daemon over localhost:7171. Plugin ships as a `.plg` package that installs a bundled Python venv and an rc.d-managed daemon.

**Tech Stack:** Python 3.11, FastAPI, uvicorn, aiosqlite, mutagen, openai-whisper, torch, httpx, ffmpeg (system), PHP 8+, vanilla JS, Unraid `.plg` packaging.

**Spec:** `docs/superpowers/specs/2026-04-24-audiobook-organizer-plugin-design.md`

---

## File Structure

```
daemon/
  main.py               # FastAPI app, all route registrations
  models.py             # All Pydantic models (shared types)
  config.py             # Config load/save via SQLite
  db.py                 # Async SQLite wrapper, schema creation
  scanner.py            # Recursive file discovery + book grouping
  identifier.py         # Orchestrates stages 1–4 per BookGroup
  confidence.py         # Confidence score calculation
  file_mover.py         # Atomic copy+verify+delete, rollback
  tag_writer.py         # mutagen tag updates after move
  pipeline/
    __init__.py
    tag_reader.py       # Stage 1: mutagen tag extraction
    filename_parser.py  # Stage 2: filename/folder name parsing
    google_books.py     # Google Books API client + SQLite cache
    stt_engine.py       # Stage 3: STT orchestrator (local/cloud)
  stt/
    __init__.py
    local_whisper.py    # openai-whisper local transcription
    openai_stt.py       # OpenAI Whisper API transcription
    google_stt.py       # Google Speech-to-Text transcription
  tests/
    conftest.py         # Shared fixtures (tmp dirs, mock audio files)
    test_scanner.py
    test_tag_reader.py
    test_filename_parser.py
    test_google_books.py
    test_confidence.py
    test_identifier.py
    test_file_mover.py
    test_tag_writer.py
    test_api.py
    test_integration.py
  requirements.txt
  pytest.ini

ui/
  AudiobookOrganizer.page   # Unraid plugin page (PHP + HTML)
  include/
    api_client.php           # PHP HTTP client → daemon
  js/
    app.js                   # Scan control, results table, approval
  css/
    style.css

plugin/
  audiobook-organizer.plg    # Unraid plugin XML manifest
  scripts/
    rc.audiobook-organizer   # rc.d start/stop/restart script
    install.sh               # Install Python venv + deps
    uninstall.sh
```

---

## Task 1: Project Skeleton + Dev Environment

**Files:**
- Create: `daemon/requirements.txt`
- Create: `daemon/pytest.ini`
- Create: `daemon/main.py`
- Create: `daemon/pipeline/__init__.py`
- Create: `daemon/stt/__init__.py`
- Create: `daemon/tests/conftest.py`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p daemon/pipeline daemon/stt daemon/tests ui/include ui/js ui/css plugin/scripts
touch daemon/pipeline/__init__.py daemon/stt/__init__.py
```

- [ ] **Step 2: Write requirements.txt**

```
fastapi==0.115.0
uvicorn[standard]==0.30.0
aiosqlite==0.20.0
mutagen==1.47.0
httpx==0.27.0
pydantic==2.7.0
openai==1.40.0
openai-whisper==20240930
torch==2.3.0
ffmpeg-python==0.2.0
pytest==8.3.0
pytest-asyncio==0.23.0
httpx==0.27.0
```

- [ ] **Step 3: Write pytest.ini**

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

- [ ] **Step 4: Write minimal FastAPI app**

```python
# daemon/main.py
from fastapi import FastAPI

app = FastAPI(title="Audiobook Organizer")

@app.get("/api/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 5: Write conftest.py with shared fixtures**

```python
# daemon/tests/conftest.py
import pytest
import tempfile
import shutil
from pathlib import Path

@pytest.fixture
def tmp_dir(tmp_path):
    yield tmp_path

@pytest.fixture
def audio_dir(tmp_path):
    """Directory with fake audio files in chaotic structure."""
    d = tmp_path / "audiobooks"
    d.mkdir()
    return d

def make_fake_mp3(path: Path, content: bytes = b"ID3" + b"\x00" * 100):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path
```

- [ ] **Step 6: Create and activate Python venv, install deps**

```bash
cd daemon
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

- [ ] **Step 7: Run health check to verify server starts**

```bash
uvicorn main:app --port 7171 &
curl http://localhost:7171/api/health
# Expected: {"status":"ok"}
kill %1
```

- [ ] **Step 8: Commit**

```bash
git add daemon/ ui/ plugin/
git commit -m "chore: project skeleton for audiobook organizer plugin"
```

---

## Task 2: SQLite Database Module

**Files:**
- Create: `daemon/db.py`
- Create: `daemon/tests/test_db.py` (implicit — tested via config tests)

- [ ] **Step 1: Write failing test**

```python
# daemon/tests/test_api.py  (bootstrap)
import pytest
from httpx import AsyncClient, ASGITransport
from main import app

@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/api/health")
    assert r.status_code == 200
```

Run: `cd daemon && pytest tests/test_api.py -v`  
Expected: PASS (health already implemented)

- [ ] **Step 2: Write db.py**

```python
# daemon/db.py
import aiosqlite
import os

DB_PATH = os.environ.get("DB_PATH", "/boot/config/plugins/audiobook-organizer/state.db")

async def get_db() -> aiosqlite.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db

async def init_db():
    async with await get_db() as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS scan_state (
                id INTEGER PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'idle',
                data TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS google_books_cache (
                query_hash TEXT PRIMARY KEY,
                response TEXT NOT NULL,
                cached_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS rollback_log (
                id INTEGER PRIMARY KEY,
                moves TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
        """)
        await db.commit()
        # Ensure scan_state has one row
        await db.execute(
            "INSERT OR IGNORE INTO scan_state (id, status, data) VALUES (1, 'idle', '{}')"
        )
        await db.commit()
```

- [ ] **Step 3: Wire init_db into app startup**

```python
# daemon/main.py
from fastapi import FastAPI
from db import init_db

app = FastAPI(title="Audiobook Organizer")

@app.on_event("startup")
async def startup():
    await init_db()

@app.get("/api/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 4: Run tests**

```bash
DB_PATH=/tmp/test-aotest.db pytest tests/test_api.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add daemon/db.py daemon/main.py daemon/tests/test_api.py
git commit -m "feat: SQLite schema and db init"
```

---

## Task 3: Pydantic Models + Config API

**Files:**
- Create: `daemon/models.py`
- Create: `daemon/config.py`
- Modify: `daemon/main.py` (add config routes)
- Create: `daemon/tests/test_config.py`

- [ ] **Step 1: Write failing tests**

```python
# daemon/tests/test_config.py
import pytest
import os
os.environ["DB_PATH"] = "/tmp/test-ao-config.db"

from httpx import AsyncClient, ASGITransport
from main import app

@pytest.fixture(autouse=True)
async def reset_db():
    from db import init_db
    await init_db()
    yield

@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

@pytest.mark.asyncio
async def test_get_config_defaults(client):
    r = await client.get("/api/config")
    assert r.status_code == 200
    data = r.json()
    assert data["confidence_threshold"] == 0.85
    assert data["stt_engine"] == "none"

@pytest.mark.asyncio
async def test_save_config(client):
    payload = {
        "source_path": "/mnt/user/audiobooks-raw",
        "dest_path": "/mnt/user/audiobooks",
        "google_books_api_key": "test-key",
        "stt_engine": "local_whisper",
        "whisper_model": "small",
        "stt_api_key": "",
        "confidence_threshold": 0.80,
    }
    r = await client.post("/api/config", json=payload)
    assert r.status_code == 200
    r2 = await client.get("/api/config")
    assert r2.json()["source_path"] == "/mnt/user/audiobooks-raw"
    assert r2.json()["confidence_threshold"] == 0.80
```

Run: `DB_PATH=/tmp/test-ao-config.db pytest tests/test_config.py -v`
Expected: FAIL — routes not found

- [ ] **Step 2: Write models.py**

```python
# daemon/models.py
from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional, List
from datetime import datetime

class STTEngine(str, Enum):
    NONE = "none"
    LOCAL_WHISPER = "local_whisper"
    OPENAI_API = "openai_api"
    GOOGLE_SPEECH = "google_speech"

class WhisperModel(str, Enum):
    TINY = "tiny"
    BASE = "base"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"

class IdentificationSource(str, Enum):
    TAGS = "tags"
    FILENAME = "filename"
    STT = "stt"
    UNIDENTIFIED = "unidentified"

class Config(BaseModel):
    source_path: str = ""
    dest_path: str = ""
    google_books_api_key: str = ""
    stt_engine: STTEngine = STTEngine.NONE
    whisper_model: WhisperModel = WhisperModel.SMALL
    stt_api_key: str = ""
    confidence_threshold: float = Field(default=0.85, ge=0.70, le=0.95)

class BookGroup(BaseModel):
    files: List[str]
    folder: str

class BookMatch(BaseModel):
    title: str
    author: str
    series: Optional[str] = None
    series_number: Optional[float] = None
    google_books_id: Optional[str] = None
    confidence: float
    source: IdentificationSource

class ProposedMove(BaseModel):
    id: str
    book_group: BookGroup
    match: Optional[BookMatch] = None
    proposed_path: Optional[str] = None
    approved: bool = True
    status: str = "pending"

class ScanStatus(str, Enum):
    IDLE = "idle"
    SCANNING = "scanning"
    AWAITING_APPROVAL = "awaiting_approval"
    MOVING = "moving"
    COMPLETE = "complete"
    ERROR = "error"

class ScanState(BaseModel):
    status: ScanStatus = ScanStatus.IDLE
    total_books: int = 0
    processed_books: int = 0
    current_book: Optional[str] = None
    proposed_moves: List[ProposedMove] = []
    manual_review: List[ProposedMove] = []
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

class ApproveRequest(BaseModel):
    approved_ids: List[str]
    write_tags: bool = False
```

- [ ] **Step 3: Write config.py**

```python
# daemon/config.py
import json
from models import Config
from db import get_db

async def load_config() -> Config:
    async with await get_db() as db:
        cursor = await db.execute("SELECT key, value FROM config")
        rows = await cursor.fetchall()
    data = {row["key"]: json.loads(row["value"]) for row in rows}
    return Config(**data)

async def save_config(cfg: Config):
    async with await get_db() as db:
        for key, value in cfg.model_dump().items():
            await db.execute(
                "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
                (key, json.dumps(value))
            )
        await db.commit()
```

- [ ] **Step 4: Add config routes to main.py**

```python
# daemon/main.py  (add to existing file)
from fastapi import FastAPI
from db import init_db
from config import load_config, save_config
from models import Config

app = FastAPI(title="Audiobook Organizer")

@app.on_event("startup")
async def startup():
    await init_db()

@app.get("/api/health")
async def health():
    return {"status": "ok"}

@app.get("/api/config", response_model=Config)
async def get_config():
    return await load_config()

@app.post("/api/config", response_model=Config)
async def post_config(cfg: Config):
    await save_config(cfg)
    return cfg
```

- [ ] **Step 5: Run tests**

```bash
DB_PATH=/tmp/test-ao-config.db pytest tests/test_config.py -v
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add daemon/models.py daemon/config.py daemon/main.py daemon/tests/test_config.py
git commit -m "feat: Pydantic models and config GET/POST API"
```

---

## Task 4: Directory Scanner + Book Grouper

**Files:**
- Create: `daemon/scanner.py`
- Create: `daemon/tests/test_scanner.py`

- [ ] **Step 1: Write failing tests**

```python
# daemon/tests/test_scanner.py
import pytest
from pathlib import Path
from tests.conftest import make_fake_mp3
from scanner import scan_for_books, AUDIO_EXTENSIONS

def test_single_file_is_one_book(tmp_path):
    make_fake_mp3(tmp_path / "The Hobbit.mp3")
    books = scan_for_books(str(tmp_path))
    assert len(books) == 1
    assert len(books[0].files) == 1

def test_chapter_files_grouped_as_one_book(tmp_path):
    folder = tmp_path / "Way of Kings"
    for i in range(3):
        make_fake_mp3(folder / f"0{i+1} - Way of Kings.mp3")
    books = scan_for_books(str(tmp_path))
    assert len(books) == 1
    assert len(books[0].files) == 3

def test_two_separate_folders_are_two_books(tmp_path):
    make_fake_mp3(tmp_path / "Book A" / "book-a.mp3")
    make_fake_mp3(tmp_path / "Book B" / "book-b.mp3")
    books = scan_for_books(str(tmp_path))
    assert len(books) == 2

def test_non_audio_files_ignored(tmp_path):
    make_fake_mp3(tmp_path / "book.mp3")
    (tmp_path / "cover.jpg").write_bytes(b"fake jpg")
    (tmp_path / "info.txt").write_text("notes")
    books = scan_for_books(str(tmp_path))
    assert len(books) == 1
    assert all(f.endswith(".mp3") for f in books[0].files)

def test_nested_directory_scan(tmp_path):
    make_fake_mp3(tmp_path / "Author" / "Series" / "Book 1" / "01.mp3")
    make_fake_mp3(tmp_path / "Author" / "Series" / "Book 2" / "01.mp3")
    books = scan_for_books(str(tmp_path))
    assert len(books) == 2

def test_files_sorted_within_book(tmp_path):
    folder = tmp_path / "Book"
    make_fake_mp3(folder / "03.mp3")
    make_fake_mp3(folder / "01.mp3")
    make_fake_mp3(folder / "02.mp3")
    books = scan_for_books(str(tmp_path))
    names = [Path(f).name for f in books[0].files]
    assert names == ["01.mp3", "02.mp3", "03.mp3"]
```

Run: `pytest tests/test_scanner.py -v`
Expected: FAIL — scanner module not found

- [ ] **Step 2: Write scanner.py**

```python
# daemon/scanner.py
from pathlib import Path
from collections import defaultdict
from models import BookGroup

AUDIO_EXTENSIONS = {".mp3", ".m4b", ".m4a", ".flac", ".ogg", ".opus", ".aac", ".wav"}

def scan_for_books(source_path: str) -> list[BookGroup]:
    root = Path(source_path)
    by_folder: dict[Path, list[Path]] = defaultdict(list)

    for f in root.rglob("*"):
        if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS:
            by_folder[f.parent].append(f)

    groups = []
    for folder, files in sorted(by_folder.items()):
        sorted_files = sorted(files)
        groups.append(BookGroup(
            files=[str(f) for f in sorted_files],
            folder=str(folder),
        ))
    return groups
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_scanner.py -v
```
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add daemon/scanner.py daemon/tests/test_scanner.py
git commit -m "feat: recursive audio file scanner and book grouper"
```

---

## Task 5: Tag Reader (Pipeline Stage 1)

**Files:**
- Create: `daemon/pipeline/tag_reader.py`
- Create: `daemon/tests/test_tag_reader.py`

- [ ] **Step 1: Write failing tests**

```python
# daemon/tests/test_tag_reader.py
import pytest
from pathlib import Path
from mutagen.id3 import ID3, TIT2, TPE1, TALB
from mutagen.mp4 import MP4
from pipeline.tag_reader import read_tags

def make_tagged_mp3(path: Path, title: str, artist: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tags = ID3()
    tags.add(TIT2(encoding=3, text=title))
    tags.add(TPE1(encoding=3, text=artist))
    tags.save(str(path))

def test_reads_title_and_author(tmp_path):
    f = tmp_path / "book.mp3"
    make_tagged_mp3(f, "The Hobbit", "J.R.R. Tolkien")
    result = read_tags(str(f))
    assert result["title"] == "The Hobbit"
    assert result["author"] == "J.R.R. Tolkien"

def test_missing_tags_returns_none_values(tmp_path):
    f = tmp_path / "untagged.mp3"
    f.write_bytes(b"\x00" * 128)
    result = read_tags(str(f))
    assert result["title"] is None
    assert result["author"] is None

def test_returns_none_on_unreadable_file(tmp_path):
    f = tmp_path / "corrupt.mp3"
    f.write_bytes(b"not audio")
    result = read_tags(str(f))
    assert result["title"] is None
```

Run: `pytest tests/test_tag_reader.py -v`
Expected: FAIL

- [ ] **Step 2: Write pipeline/tag_reader.py**

```python
# daemon/pipeline/tag_reader.py
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
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_tag_reader.py -v
```
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add daemon/pipeline/tag_reader.py daemon/tests/test_tag_reader.py
git commit -m "feat: ID3/MP4 tag reader for pipeline stage 1"
```

---

## Task 6: Filename Parser (Pipeline Stage 2)

**Files:**
- Create: `daemon/pipeline/filename_parser.py`
- Create: `daemon/tests/test_filename_parser.py`

- [ ] **Step 1: Write failing tests**

```python
# daemon/tests/test_filename_parser.py
import pytest
from pipeline.filename_parser import parse_filename, parse_folder_name

@pytest.mark.parametrize("filename,expected_title,expected_author", [
    ("The Hobbit.mp3", "The Hobbit", None),
    ("01 - The Hobbit.mp3", "The Hobbit", None),
    ("Tolkien, J.R.R. - The Hobbit.mp3", "The Hobbit", "Tolkien, J.R.R."),
    ("The Hobbit [Unabridged].mp3", "The Hobbit", None),
    ("The Hobbit narrated by Andy Serkis.mp3", "The Hobbit", None),
    ("The Hobbit (Lord of the Rings, #0).mp3", "The Hobbit", None),
    ("001_thehobbit_ch01.mp3", "thehobbit", None),
])
def test_parse_filename(filename, expected_title, expected_author):
    title, author = parse_filename(filename)
    assert title.lower() == expected_title.lower()
    if expected_author:
        assert author and expected_author.lower() in author.lower()

def test_parse_folder_name_strips_junk():
    title, author = parse_folder_name("Tolkien - The Hobbit (2001) [MP3]")
    assert "hobbit" in title.lower()
```

Run: `pytest tests/test_filename_parser.py -v`
Expected: FAIL

- [ ] **Step 2: Write pipeline/filename_parser.py**

```python
# daemon/pipeline/filename_parser.py
import re
from pathlib import Path

def parse_filename(filename: str) -> tuple[str, str | None]:
    """Returns (title_candidate, author_candidate_or_None)."""
    name = Path(filename).stem
    return _parse_name(name)

def parse_folder_name(folder_name: str) -> tuple[str, str | None]:
    return _parse_name(folder_name)

def _parse_name(name: str) -> tuple[str, str | None]:
    # Strip leading track numbers: "01 - ", "001_", "1. "
    name = re.sub(r"^\d+[\s\-_\.]+", "", name)
    # Strip bracketed content: [Unabridged], [MP3], (2001)
    name = re.sub(r"\[.*?\]", "", name)
    name = re.sub(r"\(\d{4}\)", "", name)
    # Strip series info: (Series Name, #N) or (Series Book N)
    name = re.sub(r"\s*\([^)]*[#,]\s*\d+[^)]*\)", "", name)
    name = re.sub(r"\s*\([^)]*[Bb]ook\s+\d+[^)]*\)", "", name)
    # Strip narrator credit
    name = re.sub(r"\s*(narrated|read)\s+by\s+.*", "", name, flags=re.IGNORECASE)
    # Check for "Author - Title" or "Title - Author" pattern
    parts = re.split(r"\s+-\s+", name.strip())
    if len(parts) == 2:
        # Heuristic: if first part looks like a name (contains comma or all caps), it's the author
        first, second = parts[0].strip(), parts[1].strip()
        if "," in first or re.match(r"^[A-Z][a-z]+,?\s+[A-Z]", first):
            return second, first
        return second, first  # Return both; caller decides
    return name.strip(), None
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_filename_parser.py -v
```
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add daemon/pipeline/filename_parser.py daemon/tests/test_filename_parser.py
git commit -m "feat: filename and folder name parser for pipeline stage 2"
```

---

## Task 7: Google Books API Client + Cache

**Files:**
- Create: `daemon/pipeline/google_books.py`
- Create: `daemon/tests/test_google_books.py`

- [ ] **Step 1: Write failing tests**

```python
# daemon/tests/test_google_books.py
import pytest
import os
os.environ["DB_PATH"] = "/tmp/test-ao-books.db"

import json
from unittest.mock import AsyncMock, patch
from pipeline.google_books import query_google_books, BOOKS_API_URL

@pytest.fixture(autouse=True)
async def setup_db():
    from db import init_db
    await init_db()

MOCK_RESPONSE = {
    "items": [{
        "id": "abc123",
        "volumeInfo": {
            "title": "The Hobbit",
            "authors": ["J.R.R. Tolkien"],
            "publishedDate": "1937",
            "seriesInfo": None,
        }
    }]
}

@pytest.mark.asyncio
async def test_returns_items_from_api():
    with patch("pipeline.google_books.httpx.AsyncClient") as mock_client:
        mock_resp = AsyncMock()
        mock_resp.json.return_value = MOCK_RESPONSE
        mock_resp.raise_for_status = AsyncMock()
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
        results = await query_google_books("The Hobbit", "Tolkien", api_key="fake")
    assert len(results) == 1
    assert results[0]["volumeInfo"]["title"] == "The Hobbit"

@pytest.mark.asyncio
async def test_caches_result():
    with patch("pipeline.google_books.httpx.AsyncClient") as mock_client:
        mock_resp = AsyncMock()
        mock_resp.json.return_value = MOCK_RESPONSE
        mock_resp.raise_for_status = AsyncMock()
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
        await query_google_books("The Hobbit", "Tolkien", api_key="fake")
        await query_google_books("The Hobbit", "Tolkien", api_key="fake")
        assert mock_client.return_value.__aenter__.return_value.get.call_count == 1

@pytest.mark.asyncio
async def test_returns_empty_list_on_api_error():
    with patch("pipeline.google_books.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(side_effect=Exception("network"))
        results = await query_google_books("Bad Query", None, api_key="fake")
    assert results == []
```

Run: `pytest tests/test_google_books.py -v`
Expected: FAIL

- [ ] **Step 2: Write pipeline/google_books.py**

```python
# daemon/pipeline/google_books.py
import hashlib
import json
import asyncio
import httpx
from datetime import datetime
from db import get_db

BOOKS_API_URL = "https://www.googleapis.com/books/v1/volumes"
_rate_limit = asyncio.Semaphore(1)
_last_request_time = 0.0

async def query_google_books(
    title: str, author: str | None, api_key: str
) -> list[dict]:
    if not api_key or not title:
        return []

    query = f'intitle:"{title}"'
    if author:
        query += f' inauthor:"{author}"'
    cache_key = hashlib.md5(query.encode()).hexdigest()

    cached = await _get_cache(cache_key)
    if cached is not None:
        return cached

    global _last_request_time
    async with _rate_limit:
        import time
        elapsed = time.time() - _last_request_time
        if elapsed < 1.0:
            await asyncio.sleep(1.0 - elapsed)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(
                    BOOKS_API_URL,
                    params={"q": query, "key": api_key, "maxResults": 5, "printType": "books"},
                )
                r.raise_for_status()
                data = r.json()
                items = data.get("items", [])
        except Exception:
            return []
        finally:
            _last_request_time = time.time()

    await _set_cache(cache_key, items)
    return items

async def _get_cache(key: str) -> list[dict] | None:
    async with await get_db() as db:
        cursor = await db.execute(
            "SELECT response FROM google_books_cache WHERE query_hash = ?", (key,)
        )
        row = await cursor.fetchone()
        if row:
            return json.loads(row["response"])
    return None

async def _set_cache(key: str, items: list[dict]):
    async with await get_db() as db:
        await db.execute(
            "INSERT OR REPLACE INTO google_books_cache (query_hash, response, cached_at) VALUES (?, ?, ?)",
            (key, json.dumps(items), datetime.utcnow().isoformat()),
        )
        await db.commit()
```

- [ ] **Step 3: Run tests**

```bash
DB_PATH=/tmp/test-ao-books.db pytest tests/test_google_books.py -v
```
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add daemon/pipeline/google_books.py daemon/tests/test_google_books.py
git commit -m "feat: Google Books API client with SQLite caching"
```

---

## Task 8: Confidence Scorer

**Files:**
- Create: `daemon/confidence.py`
- Create: `daemon/tests/test_confidence.py`

- [ ] **Step 1: Write failing tests**

```python
# daemon/tests/test_confidence.py
from confidence import score_candidate

HOBBIT_CANDIDATE = {
    "id": "abc",
    "volumeInfo": {
        "title": "The Hobbit",
        "authors": ["J.R.R. Tolkien"],
        "publishedDate": "1937",
    }
}

def test_exact_match_scores_high():
    s = score_candidate("The Hobbit", "J.R.R. Tolkien", HOBBIT_CANDIDATE)
    assert s >= 0.90

def test_partial_title_match_scores_medium():
    s = score_candidate("Hobbit", "Tolkien", HOBBIT_CANDIDATE)
    assert 0.50 <= s < 0.90

def test_wrong_book_scores_low():
    s = score_candidate("Harry Potter", "Rowling", HOBBIT_CANDIDATE)
    assert s < 0.30

def test_no_author_query_still_scores_on_title():
    s = score_candidate("The Hobbit", None, HOBBIT_CANDIDATE)
    assert s >= 0.55

def test_score_is_between_zero_and_one():
    s = score_candidate("anything", "anyone", HOBBIT_CANDIDATE)
    assert 0.0 <= s <= 1.0
```

Run: `pytest tests/test_confidence.py -v`
Expected: FAIL

- [ ] **Step 2: Write confidence.py**

```python
# daemon/confidence.py
from difflib import SequenceMatcher

def score_candidate(query_title: str, query_author: str | None, candidate: dict) -> float:
    info = candidate.get("volumeInfo", {})
    book_title = info.get("title", "")
    book_authors = info.get("authors", [])

    title_sim = SequenceMatcher(
        None, query_title.lower().strip(), book_title.lower().strip()
    ).ratio()

    if book_authors and query_author:
        author_sim = max(
            SequenceMatcher(None, query_author.lower(), a.lower()).ratio()
            for a in book_authors
        )
    elif not query_author:
        author_sim = 0.5  # neutral — no author to compare
    else:
        author_sim = 0.0

    return round(title_sim * 0.65 + author_sim * 0.35, 4)

def best_candidate(
    query_title: str, query_author: str | None, candidates: list[dict], threshold: float
) -> tuple[dict | None, float]:
    """Returns (best_candidate_or_None, score). None if no candidate exceeds threshold."""
    if not candidates:
        return None, 0.0
    scored = [(c, score_candidate(query_title, query_author, c)) for c in candidates]
    best, score = max(scored, key=lambda x: x[1])
    if score >= threshold:
        return best, score
    return None, score
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_confidence.py -v
```
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add daemon/confidence.py daemon/tests/test_confidence.py
git commit -m "feat: confidence scorer for Google Books candidates"
```

---

## Task 9: STT Engines (Local Whisper + Cloud)

**Files:**
- Create: `daemon/stt/local_whisper.py`
- Create: `daemon/stt/openai_stt.py`
- Create: `daemon/stt/google_stt.py`
- Create: `daemon/pipeline/stt_engine.py`

Note: STT tests use mocks — do not call actual APIs or load Whisper models in tests.

- [ ] **Step 1: Write stt/local_whisper.py**

```python
# daemon/stt/local_whisper.py
import subprocess
import tempfile
import os
from pathlib import Path

def extract_audio_chunk(input_path: str, duration_seconds: int = 600) -> str:
    """Use ffmpeg to extract first N seconds as 16kHz mono WAV. Returns temp file path."""
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    subprocess.run([
        "ffmpeg", "-y", "-i", input_path,
        "-t", str(duration_seconds),
        "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        tmp.name
    ], capture_output=True, check=True)
    return tmp.name

def transcribe_local(audio_path: str, model_name: str = "small") -> str:
    """Transcribe audio file using local Whisper. Returns transcript text."""
    import whisper
    model = whisper.load_model(model_name)
    result = model.transcribe(audio_path, language="en", fp16=False)
    return result.get("text", "")
```

- [ ] **Step 2: Write stt/openai_stt.py**

```python
# daemon/stt/openai_stt.py
import os
from pathlib import Path

def transcribe_openai(audio_path: str, api_key: str) -> str:
    """Transcribe using OpenAI Whisper API. Returns transcript text."""
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    with open(audio_path, "rb") as f:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="text",
        )
    return transcript if isinstance(transcript, str) else transcript.text
```

- [ ] **Step 3: Write stt/google_stt.py**

```python
# daemon/stt/google_stt.py
import base64
import httpx

async def transcribe_google(audio_path: str, api_key: str) -> str:
    """Transcribe using Google Speech-to-Text REST API. Returns transcript text."""
    with open(audio_path, "rb") as f:
        audio_content = base64.b64encode(f.read()).decode()

    payload = {
        "config": {
            "encoding": "LINEAR16",
            "sampleRateHertz": 16000,
            "languageCode": "en-US",
            "model": "default",
        },
        "audio": {"content": audio_content},
    }
    url = f"https://speech.googleapis.com/v1/speech:recognize?key={api_key}"
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(url, json=payload)
        r.raise_for_status()
        data = r.json()

    results = data.get("results", [])
    return " ".join(
        alt["transcript"]
        for r in results
        for alt in r.get("alternatives", [])[:1]
    )
```

- [ ] **Step 4: Write pipeline/stt_engine.py**

```python
# daemon/pipeline/stt_engine.py
import tempfile
import os
from models import STTEngine
from stt.local_whisper import extract_audio_chunk, transcribe_local

STT_CHUNK_SECONDS = 600  # 10 minutes

async def transcribe_book(
    first_file: str,
    engine: STTEngine,
    whisper_model: str = "small",
    api_key: str = "",
) -> str | None:
    """Extract first 10 min of audio and transcribe. Returns text or None on failure."""
    if engine == STTEngine.NONE:
        return None

    tmp_wav = None
    try:
        tmp_wav = extract_audio_chunk(first_file, STT_CHUNK_SECONDS)

        if engine == STTEngine.LOCAL_WHISPER:
            return transcribe_local(tmp_wav, whisper_model)
        elif engine == STTEngine.OPENAI_API:
            from stt.openai_stt import transcribe_openai
            return transcribe_openai(tmp_wav, api_key)
        elif engine == STTEngine.GOOGLE_SPEECH:
            from stt.google_stt import transcribe_google
            return await transcribe_google(tmp_wav, api_key)
    except Exception:
        return None
    finally:
        if tmp_wav and os.path.exists(tmp_wav):
            os.unlink(tmp_wav)

def extract_title_from_transcript(transcript: str) -> tuple[str | None, str | None]:
    """Look for 'This is [Title] by [Author]' or repeated title patterns."""
    import re
    # Pattern: "This is <Title> by <Author>" or "I'm reading <Title> by <Author>"
    m = re.search(
        r"(?:this is|i[''`]?m reading|welcome to)\s+(.+?)\s+by\s+([A-Z][a-zA-Z\s,\.]+)",
        transcript, re.IGNORECASE
    )
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return None, None
```

- [ ] **Step 5: Write test for STT engine orchestrator (mocked)**

```python
# daemon/tests/test_stt.py
import pytest
from unittest.mock import patch, AsyncMock
from models import STTEngine
from pipeline.stt_engine import extract_title_from_transcript, transcribe_book

def test_extract_title_from_transcript_standard_intro():
    text = "This is The Hobbit by J.R.R. Tolkien. Chapter one..."
    title, author = extract_title_from_transcript(text)
    assert title and "hobbit" in title.lower()
    assert author and "tolkien" in author.lower()

def test_extract_title_returns_none_when_no_pattern():
    title, author = extract_title_from_transcript("blah blah blah no title here")
    assert title is None

@pytest.mark.asyncio
async def test_transcribe_returns_none_when_engine_none(tmp_path):
    f = tmp_path / "audio.mp3"
    f.write_bytes(b"\x00" * 100)
    result = await transcribe_book(str(f), STTEngine.NONE)
    assert result is None
```

Run: `pytest tests/test_stt.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add daemon/stt/ daemon/pipeline/stt_engine.py daemon/tests/test_stt.py
git commit -m "feat: STT engines (local Whisper, OpenAI API, Google Speech)"
```

---

## Task 10: Identification Pipeline Orchestrator

**Files:**
- Create: `daemon/identifier.py`
- Create: `daemon/tests/test_identifier.py`

- [ ] **Step 1: Write failing tests**

```python
# daemon/tests/test_identifier.py
import pytest
import os
os.environ["DB_PATH"] = "/tmp/test-ao-identifier.db"

from unittest.mock import patch, AsyncMock
from models import BookGroup, IdentificationSource, Config, STTEngine
from identifier import identify_book

HOBBIT_CANDIDATE = {
    "id": "abc",
    "volumeInfo": {
        "title": "The Hobbit",
        "authors": ["J.R.R. Tolkien"],
        "seriesInfo": {"bookSeries": [{"seriesId": "xyz", "orderNumber": "0"}]},
    }
}

@pytest.fixture(autouse=True)
async def setup_db():
    from db import init_db
    await init_db()

@pytest.mark.asyncio
async def test_identifies_via_tags():
    group = BookGroup(files=["/fake/hobbit.mp3"], folder="/fake")
    cfg = Config(google_books_api_key="key", confidence_threshold=0.85)

    with patch("identifier.read_tags", return_value={"title": "The Hobbit", "author": "J.R.R. Tolkien"}), \
         patch("identifier.query_google_books", AsyncMock(return_value=[HOBBIT_CANDIDATE])):
        match = await identify_book(group, cfg)

    assert match is not None
    assert match.source == IdentificationSource.TAGS
    assert "hobbit" in match.title.lower()

@pytest.mark.asyncio
async def test_falls_through_to_filename_when_no_tags():
    group = BookGroup(files=["/fake/Tolkien - The Hobbit.mp3"], folder="/fake")
    cfg = Config(google_books_api_key="key", confidence_threshold=0.85)

    with patch("identifier.read_tags", return_value={"title": None, "author": None}), \
         patch("identifier.query_google_books", AsyncMock(return_value=[HOBBIT_CANDIDATE])):
        match = await identify_book(group, cfg)

    assert match is not None
    assert match.source == IdentificationSource.FILENAME

@pytest.mark.asyncio
async def test_returns_none_when_no_match_found():
    group = BookGroup(files=["/fake/gibberish_xyz.mp3"], folder="/fake")
    cfg = Config(google_books_api_key="key", confidence_threshold=0.85)

    with patch("identifier.read_tags", return_value={"title": None, "author": None}), \
         patch("identifier.query_google_books", AsyncMock(return_value=[])):
        match = await identify_book(group, cfg)

    assert match is None
```

Run: `pytest tests/test_identifier.py -v`
Expected: FAIL

- [ ] **Step 2: Write identifier.py**

```python
# daemon/identifier.py
import re
from models import BookGroup, BookMatch, IdentificationSource, Config, STTEngine
from pipeline.tag_reader import read_tags
from pipeline.filename_parser import parse_filename, parse_folder_name
from pipeline.google_books import query_google_books
from pipeline.stt_engine import transcribe_book, extract_title_from_transcript
from confidence import best_candidate
from pathlib import Path

async def identify_book(group: BookGroup, cfg: Config) -> BookMatch | None:
    first_file = group.files[0]
    threshold = cfg.confidence_threshold

    # Stage 1: ID3 tags
    tags = read_tags(first_file)
    if tags["title"]:
        candidates = await query_google_books(tags["title"], tags["author"], cfg.google_books_api_key)
        best, score = best_candidate(tags["title"], tags["author"], candidates, threshold)
        if best:
            return _make_match(best, score, IdentificationSource.TAGS)

    # Stage 2: Filename parsing
    fname_title, fname_author = parse_filename(Path(first_file).name)
    if not fname_title:
        folder_title, folder_author = parse_folder_name(Path(group.folder).name)
        fname_title, fname_author = folder_title, folder_author

    if fname_title and len(fname_title) > 3:
        candidates = await query_google_books(fname_title, fname_author, cfg.google_books_api_key)
        best, score = best_candidate(fname_title, fname_author, candidates, threshold)
        if best:
            return _make_match(best, score, IdentificationSource.FILENAME)

    # Stage 3: STT
    if cfg.stt_engine != STTEngine.NONE:
        transcript = await transcribe_book(
            first_file, cfg.stt_engine, cfg.whisper_model, cfg.stt_api_key
        )
        if transcript:
            stt_title, stt_author = extract_title_from_transcript(transcript)
            if stt_title:
                candidates = await query_google_books(stt_title, stt_author, cfg.google_books_api_key)
                best, score = best_candidate(stt_title, stt_author, candidates, threshold)
                if best:
                    return _make_match(best, score, IdentificationSource.STT)

    # Stage 4: No match
    return None

def _make_match(candidate: dict, score: float, source: IdentificationSource) -> BookMatch:
    info = candidate.get("volumeInfo", {})
    authors = info.get("authors", [])
    author = authors[0] if authors else "Unknown"

    series = None
    series_number = None
    series_info = info.get("seriesInfo", {})
    if series_info and series_info.get("bookSeries"):
        first_series = series_info["bookSeries"][0]
        series = first_series.get("seriesId")
        try:
            series_number = float(first_series.get("orderNumber", ""))
        except (ValueError, TypeError):
            pass

    return BookMatch(
        title=info.get("title", "Unknown"),
        author=author,
        series=series,
        series_number=series_number,
        google_books_id=candidate.get("id"),
        confidence=score,
        source=source,
    )
```

- [ ] **Step 3: Run tests**

```bash
DB_PATH=/tmp/test-ao-identifier.db pytest tests/test_identifier.py -v
```
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add daemon/identifier.py daemon/tests/test_identifier.py
git commit -m "feat: 4-stage identification pipeline orchestrator"
```

---

## Task 11: Proposed Path Builder

**Files:**
- Create: `daemon/path_builder.py`
- Create: `daemon/tests/test_path_builder.py`

- [ ] **Step 1: Write failing tests**

```python
# daemon/tests/test_path_builder.py
from path_builder import build_proposed_path
from models import BookMatch, IdentificationSource

def match(title, author, series=None, series_number=None):
    return BookMatch(
        title=title, author=author, series=series, series_number=series_number,
        confidence=0.95, source=IdentificationSource.TAGS
    )

def test_standalone_book_path():
    path = build_proposed_path(match("The Shining", "King, Stephen"), "/library")
    assert path == "/library/King, Stephen/The Shining"

def test_series_book_path():
    path = build_proposed_path(
        match("The Way of Kings", "Sanderson, Brandon", "Stormlight Archive", 1.0),
        "/library"
    )
    assert path == "/library/Sanderson, Brandon/Stormlight Archive/1 - The Way of Kings"

def test_sanitizes_special_chars():
    path = build_proposed_path(match("Book: A Story", "O'Brien, Tim"), "/library")
    assert ":" not in path
    assert "/" not in path.replace("/library/", "")

def test_fractional_series_number():
    path = build_proposed_path(
        match("A Hobbit's Tale", "Tolkien, J.R.R.", "Middle Earth", 0.5),
        "/library"
    )
    assert "0.5" in path
```

Run: `pytest tests/test_path_builder.py -v`
Expected: FAIL

- [ ] **Step 2: Write path_builder.py**

```python
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
    # Remove characters illegal in most filesystems
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    # Collapse multiple spaces
    name = re.sub(r"\s+", " ", name).strip()
    return name
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_path_builder.py -v
```
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add daemon/path_builder.py daemon/tests/test_path_builder.py
git commit -m "feat: proposed destination path builder"
```

---

## Task 12: File Mover (Atomic + Rollback)

**Files:**
- Create: `daemon/file_mover.py`
- Create: `daemon/tests/test_file_mover.py`

- [ ] **Step 1: Write failing tests**

```python
# daemon/tests/test_file_mover.py
import pytest
import os
os.environ["DB_PATH"] = "/tmp/test-ao-mover.db"

from pathlib import Path
from tests.conftest import make_fake_mp3
from file_mover import move_book_files, undo_moves, MoveError

@pytest.fixture(autouse=True)
async def setup_db():
    from db import init_db
    await init_db()

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

@pytest.mark.asyncio
async def test_undo_moves_file_back(tmp_path):
    src = make_fake_mp3(tmp_path / "src" / "book.mp3")
    dest = tmp_path / "dest"
    moves = move_book_files([str(src)], str(dest))
    await undo_moves(moves)
    assert src.exists()
    assert not (dest / "book.mp3").exists()
```

Run: `pytest tests/test_file_mover.py -v`
Expected: FAIL

- [ ] **Step 2: Write file_mover.py**

```python
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
    """Atomically move files to dest_folder. Returns move records for rollback."""
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
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_file_mover.py -v
```
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add daemon/file_mover.py daemon/tests/test_file_mover.py
git commit -m "feat: atomic file mover with checksum verification and rollback"
```

---

## Task 13: Tag Writer

**Files:**
- Create: `daemon/tag_writer.py`
- Create: `daemon/tests/test_tag_writer.py`

- [ ] **Step 1: Write failing tests**

```python
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
    write_tags_to_files([str(f)], match)  # Should not raise
```

Run: `pytest tests/test_tag_writer.py -v`
Expected: FAIL

- [ ] **Step 2: Write tag_writer.py**

```python
# daemon/tag_writer.py
from pathlib import Path
from models import BookMatch

def write_tags_to_files(file_paths: list[str], match: BookMatch):
    for path_str in file_paths:
        try:
            _write_tags(path_str, match)
        except Exception:
            pass  # Never abort the batch for one bad file

def _write_tags(path_str: str, match: BookMatch):
    import mutagen
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
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_tag_writer.py -v
```
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add daemon/tag_writer.py daemon/tests/test_tag_writer.py
git commit -m "feat: mutagen-based tag writer for MP3 and M4B files"
```

---

## Task 14: Scan API Endpoints

**Files:**
- Modify: `daemon/main.py` (add scan routes)
- Create: `daemon/scan_worker.py`
- Create: `daemon/tests/test_scan_api.py`

- [ ] **Step 1: Write failing tests**

```python
# daemon/tests/test_scan_api.py
import pytest
import os
os.environ["DB_PATH"] = "/tmp/test-ao-scan.db"

from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from main import app

@pytest.fixture(autouse=True)
async def setup_db():
    from db import init_db
    await init_db()

@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

@pytest.mark.asyncio
async def test_scan_status_idle(client):
    r = await client.get("/api/scan/status")
    assert r.status_code == 200
    assert r.json()["status"] == "idle"

@pytest.mark.asyncio
async def test_start_scan_returns_accepted(client, tmp_path):
    (tmp_path / "book.mp3").write_bytes(b"\x00" * 100)
    with patch("scan_worker.run_scan", AsyncMock()):
        r = await client.post("/api/scan/start")
    assert r.status_code in (200, 202)

@pytest.mark.asyncio
async def test_approve_empty_list_returns_ok(client):
    r = await client.post("/api/scan/approve", json={"approved_ids": [], "write_tags": False})
    assert r.status_code == 200
```

Run: `pytest tests/test_scan_api.py::test_scan_status_idle -v`
Expected: FAIL — route not found

- [ ] **Step 2: Write scan_worker.py**

```python
# daemon/scan_worker.py
import json
import asyncio
import logging
import os
from datetime import datetime
from models import ScanState, ScanStatus, ProposedMove, Config
from scanner import scan_for_books
from identifier import identify_book
from path_builder import build_proposed_path
from db import get_db
import uuid

LOG_PATH = os.environ.get(
    "LOG_PATH",
    "/boot/config/plugins/audiobook-organizer/audiobook-organizer.log"
)
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("ao")

async def load_scan_state() -> ScanState:
    async with await get_db() as db:
        cursor = await db.execute("SELECT data FROM scan_state WHERE id = 1")
        row = await cursor.fetchone()
        if row:
            return ScanState.model_validate_json(row["data"])
    return ScanState()

async def save_scan_state(state: ScanState):
    async with await get_db() as db:
        await db.execute(
            "UPDATE scan_state SET status = ?, data = ? WHERE id = 1",
            (state.status.value, state.model_dump_json()),
        )
        await db.commit()

async def run_scan(cfg: Config):
    state = ScanState(status=ScanStatus.SCANNING, started_at=datetime.utcnow())
    await save_scan_state(state)

    try:
        groups = scan_for_books(cfg.source_path)
        state.total_books = len(groups)
        await save_scan_state(state)

        for group in groups:
            state.current_book = group.folder
            state.processed_books += 1
            await save_scan_state(state)

            match = await identify_book(group, cfg)
            move_id = str(uuid.uuid4())

            if match:
                proposed_path = build_proposed_path(match, cfg.dest_path)
                logger.info(
                    "MATCH folder=%s source=%s confidence=%.2f proposed=%s",
                    group.folder, match.source.value, match.confidence, proposed_path
                )
                proposed = ProposedMove(
                    id=move_id, book_group=group, match=match,
                    proposed_path=proposed_path, approved=True
                )
                state.proposed_moves.append(proposed)
            else:
                logger.info("NO_MATCH folder=%s → manual review", group.folder)
                flagged = ProposedMove(
                    id=move_id, book_group=group, match=None,
                    proposed_path=None, approved=False
                )
                state.manual_review.append(flagged)

        state.status = ScanStatus.AWAITING_APPROVAL
        state.completed_at = datetime.utcnow()
    except Exception as e:
        state.status = ScanStatus.ERROR
        state.error = str(e)

    await save_scan_state(state)
```

- [ ] **Step 3: Add scan routes to main.py**

```python
# daemon/main.py — replace with full file content
from fastapi import FastAPI, BackgroundTasks, HTTPException
from db import init_db
from config import load_config, save_config
from models import Config, ApproveRequest, ScanStatus
from scan_worker import load_scan_state, save_scan_state, run_scan
from file_mover import move_book_files, undo_moves, MoveRecord
from tag_writer import write_tags_to_files
import json

app = FastAPI(title="Audiobook Organizer")

@app.on_event("startup")
async def startup():
    await init_db()

@app.get("/api/health")
async def health():
    return {"status": "ok"}

@app.get("/api/config", response_model=Config)
async def get_config():
    return await load_config()

@app.post("/api/config", response_model=Config)
async def post_config(cfg: Config):
    await save_config(cfg)
    return cfg

@app.get("/api/scan/status")
async def scan_status():
    return await load_scan_state()

@app.post("/api/scan/start", status_code=202)
async def start_scan(background_tasks: BackgroundTasks):
    state = await load_scan_state()
    if state.status == ScanStatus.SCANNING:
        raise HTTPException(409, "Scan already in progress")
    cfg = await load_config()
    if not cfg.source_path or not cfg.dest_path:
        raise HTTPException(400, "Configure source and destination paths first")
    background_tasks.add_task(run_scan, cfg)
    return {"message": "Scan started"}

@app.post("/api/scan/approve")
async def approve_moves(req: ApproveRequest):
    state = await load_scan_state()
    if state.status != ScanStatus.AWAITING_APPROVAL:
        raise HTTPException(400, "No scan awaiting approval")

    approved = [m for m in state.proposed_moves if m.id in req.approved_ids]
    all_records: list[MoveRecord] = []

    state.status = ScanStatus.MOVING
    await save_scan_state(state)

    errors = []
    for move in approved:
        try:
            records = move_book_files(move.book_group.files, move.proposed_path)
            all_records.extend(records)
            if req.write_tags and move.match:
                write_tags_to_files(
                    [r.dst for r in records], move.match
                )
            move.status = "moved"
        except Exception as e:
            move.status = "failed"
            errors.append(str(e))

    # Persist rollback log
    from db import get_db
    from datetime import datetime
    async with await get_db() as db:
        await db.execute(
            "INSERT INTO rollback_log (moves, created_at) VALUES (?, ?)",
            (json.dumps([{"src": r.src, "dst": r.dst} for r in all_records]),
             datetime.utcnow().isoformat())
        )
        await db.commit()

    state.status = ScanStatus.COMPLETE
    await save_scan_state(state)
    return {"moved": len([m for m in approved if m.status == "moved"]), "errors": errors}

@app.post("/api/scan/undo")
async def undo_last_scan():
    from db import get_db
    async with await get_db() as db:
        cursor = await db.execute(
            "SELECT id, moves FROM rollback_log ORDER BY id DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(404, "No moves to undo")
        records = [MoveRecord(**r) for r in json.loads(row["moves"])]
        await undo_moves(records)
        await db.execute("DELETE FROM rollback_log WHERE id = ?", (row["id"],))
        await db.commit()
    return {"message": "Undo complete", "reversed": len(records)}
```

- [ ] **Step 4: Run tests**

```bash
DB_PATH=/tmp/test-ao-scan.db pytest tests/test_scan_api.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add daemon/scan_worker.py daemon/main.py daemon/tests/test_scan_api.py
git commit -m "feat: scan start/status/approve/undo API endpoints"
```

---

## Task 15: Manual Review API

**Files:**
- Modify: `daemon/main.py` (add manual review routes)
- Create: `daemon/tests/test_manual_review.py`

- [ ] **Step 1: Write failing tests**

```python
# daemon/tests/test_manual_review.py
import pytest
import os
os.environ["DB_PATH"] = "/tmp/test-ao-review.db"

from httpx import AsyncClient, ASGITransport
from main import app

@pytest.fixture(autouse=True)
async def setup_db():
    from db import init_db
    await init_db()

@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

@pytest.mark.asyncio
async def test_get_manual_review_empty(client):
    r = await client.get("/api/manual-review")
    assert r.status_code == 200
    assert r.json() == []

@pytest.mark.asyncio
async def test_move_to_unidentified_returns_404_when_no_such_id(client):
    r = await client.post("/api/manual-review/nonexistent/move-unidentified")
    assert r.status_code == 404
```

Run: `pytest tests/test_manual_review.py -v`
Expected: FAIL

- [ ] **Step 2: Add manual review routes to main.py**

Add these routes to the existing `daemon/main.py`:

```python
@app.get("/api/manual-review")
async def get_manual_review():
    state = await load_scan_state()
    return state.manual_review

@app.post("/api/manual-review/{item_id}/move-unidentified")
async def move_to_unidentified(item_id: str):
    state = await load_scan_state()
    item = next((m for m in state.manual_review if m.id == item_id), None)
    if not item:
        raise HTTPException(404, "Item not found")
    cfg = await load_config()
    dest = f"{cfg.dest_path}/_unidentified"
    try:
        records = move_book_files(item.book_group.files, dest)
        item.status = "moved"
        await save_scan_state(state)
        return {"moved": len(records)}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/logs")
async def get_logs():
    import os
    log_path = "/boot/config/plugins/audiobook-organizer/audiobook-organizer.log"
    if not os.path.exists(log_path):
        return {"lines": []}
    with open(log_path) as f:
        lines = f.readlines()[-200:]
    return {"lines": [l.rstrip() for l in lines]}
```

- [ ] **Step 3: Run all daemon tests**

```bash
DB_PATH=/tmp/test-ao-review.db pytest tests/ -v --ignore=tests/test_integration.py
```
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add daemon/main.py daemon/tests/test_manual_review.py
git commit -m "feat: manual review and logs API endpoints"
```

---

## Task 16: PHP UI — Config Page

**Files:**
- Create: `ui/include/api_client.php`
- Create: `ui/AudiobookOrganizer.page`
- Create: `ui/css/style.css`

Note: Unraid plugin pages use a specific `.page` file format. The page lives at `/usr/local/emhttp/plugins/audiobook-organizer/`. AJAX calls go to PHP include files.

- [ ] **Step 1: Write api_client.php**

```php
<?php
// ui/include/api_client.php
define('DAEMON_URL', 'http://127.0.0.1:7171');

function daemon_get(string $path): array {
    $ch = curl_init(DAEMON_URL . $path);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT => 10,
    ]);
    $body = curl_exec($ch);
    $code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    if ($body === false || $code >= 400) return ['error' => "HTTP $code"];
    return json_decode($body, true) ?? ['error' => 'Invalid JSON'];
}

function daemon_post(string $path, array $data = []): array {
    $ch = curl_init(DAEMON_URL . $path);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_POST => true,
        CURLOPT_POSTFIELDS => json_encode($data),
        CURLOPT_HTTPHEADER => ['Content-Type: application/json'],
        CURLOPT_TIMEOUT => 10,
    ]);
    $body = curl_exec($ch);
    $code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    if ($body === false || $code >= 400) return ['error' => "HTTP $code"];
    return json_decode($body, true) ?? ['error' => 'Invalid JSON'];
}
```

- [ ] **Step 2: Write AudiobookOrganizer.page**

```
Menu="Tools"
Title="Audiobook Organizer"
Icon="music"
---
<?php
require_once '/usr/local/emhttp/plugins/audiobook-organizer/include/api_client.php';

// Handle AJAX sub-actions via ?action=...
if (isset($_GET['action'])) {
    header('Content-Type: application/json');
    switch ($_GET['action']) {
        case 'config_get':
            echo json_encode(daemon_get('/api/config'));
            break;
        case 'config_save':
            $data = json_decode(file_get_contents('php://input'), true);
            echo json_encode(daemon_post('/api/config', $data));
            break;
        case 'scan_start':
            echo json_encode(daemon_post('/api/scan/start'));
            break;
        case 'scan_status':
            echo json_encode(daemon_get('/api/scan/status'));
            break;
        case 'scan_approve':
            $data = json_decode(file_get_contents('php://input'), true);
            echo json_encode(daemon_post('/api/scan/approve', $data));
            break;
        case 'scan_undo':
            echo json_encode(daemon_post('/api/scan/undo'));
            break;
        case 'manual_review':
            echo json_encode(daemon_get('/api/manual-review'));
            break;
        case 'move_unidentified':
            $id = $_GET['id'] ?? '';
            echo json_encode(daemon_post("/api/manual-review/{$id}/move-unidentified"));
            break;
        case 'logs':
            echo json_encode(daemon_get('/api/logs'));
            break;
    }
    exit;
}

// Check daemon status
$health = daemon_get('/api/health');
$daemon_up = !isset($health['error']);
$config = $daemon_up ? daemon_get('/api/config') : [];
?>
<!DOCTYPE html>
<html>
<head>
<link rel="stylesheet" href="/plugins/audiobook-organizer/css/style.css">
</head>
<body>
<?php if (!$daemon_up): ?>
<div class="error-banner">Audiobook Organizer daemon is not running. Check plugin logs.</div>
<?php else: ?>

<div id="ao-app">
  <!-- Tab navigation -->
  <div class="ao-tabs">
    <button class="ao-tab active" data-tab="config">Configuration</button>
    <button class="ao-tab" data-tab="scan">Scan &amp; Organize</button>
    <button class="ao-tab" data-tab="review">Manual Review</button>
    <button class="ao-tab" data-tab="logs">Logs</button>
  </div>

  <!-- Config tab -->
  <div id="tab-config" class="ao-tabcontent active">
    <h2>Configuration</h2>
    <table class="ao-form">
      <tr><td>Source path</td><td><input id="cfg-source" type="text" value="<?= htmlspecialchars($config['source_path'] ?? '') ?>"></td></tr>
      <tr><td>Destination path</td><td><input id="cfg-dest" type="text" value="<?= htmlspecialchars($config['dest_path'] ?? '') ?>"></td></tr>
      <tr><td>Google Books API key</td><td><input id="cfg-gbkey" type="text" value="<?= htmlspecialchars($config['google_books_api_key'] ?? '') ?>"></td></tr>
      <tr><td>STT engine</td>
          <td><select id="cfg-stt">
            <option value="none">None</option>
            <option value="local_whisper">Local Whisper</option>
            <option value="openai_api">OpenAI API</option>
            <option value="google_speech">Google Speech</option>
          </select></td></tr>
      <tr id="cfg-whisper-row"><td>Whisper model</td>
          <td><select id="cfg-whisper-model">
            <option value="tiny">tiny (fastest, least accurate)</option>
            <option value="base">base</option>
            <option value="small" selected>small (recommended)</option>
            <option value="medium">medium</option>
            <option value="large">large (slowest, most accurate)</option>
          </select></td></tr>
      <tr id="cfg-apikey-row"><td>STT API key</td><td><input id="cfg-sttkey" type="text" value="<?= htmlspecialchars($config['stt_api_key'] ?? '') ?>"></td></tr>
      <tr><td>Confidence threshold</td><td><input id="cfg-threshold" type="range" min="70" max="95" value="<?= (int)(($config['confidence_threshold'] ?? 0.85) * 100) ?>"> <span id="cfg-threshold-val"></span></td></tr>
    </table>
    <button id="cfg-save-btn" class="btn-primary">Save Configuration</button>
    <div id="cfg-status"></div>
  </div>

  <!-- Scan tab -->
  <div id="tab-scan" class="ao-tabcontent">
    <h2>Scan &amp; Organize</h2>
    <div id="scan-controls">
      <button id="scan-start-btn" class="btn-primary">Start Scan</button>
      <button id="scan-undo-btn" class="btn-secondary">Undo Last Scan</button>
    </div>
    <div id="scan-progress" style="display:none">
      <p>Scanning: <span id="scan-current"></span></p>
      <progress id="scan-bar" value="0" max="100"></progress>
    </div>
    <div id="scan-results" style="display:none">
      <h3>Proposed Changes</h3>
      <label><input type="checkbox" id="write-tags-toggle"> Write tags after move</label>
      <table id="results-table">
        <thead><tr><th>Select</th><th>Current path</th><th>Proposed path</th><th>Confidence</th><th>Source</th></tr></thead>
        <tbody id="results-body"></tbody>
      </table>
      <button id="apply-btn" class="btn-primary">Apply Selected</button>
    </div>
  </div>

  <!-- Manual review tab -->
  <div id="tab-review" class="ao-tabcontent">
    <h2>Manual Review</h2>
    <p>Books that could not be identified automatically.</p>
    <table id="review-table">
      <thead><tr><th>Folder</th><th>Files</th><th>Action</th></tr></thead>
      <tbody id="review-body"></tbody>
    </table>
  </div>

  <!-- Logs tab -->
  <div id="tab-logs" class="ao-tabcontent">
    <h2>Logs</h2>
    <button id="logs-refresh-btn">Refresh</button>
    <pre id="logs-content"></pre>
  </div>
</div>

<script src="/plugins/audiobook-organizer/js/app.js"></script>
<?php endif; ?>
</body>
</html>
```

- [ ] **Step 3: Write style.css**

```css
/* ui/css/style.css */
#ao-app { font-family: sans-serif; max-width: 1200px; padding: 16px; }
.ao-tabs { border-bottom: 2px solid #ddd; margin-bottom: 16px; }
.ao-tab { padding: 8px 16px; border: none; background: none; cursor: pointer; font-size: 14px; }
.ao-tab.active { border-bottom: 2px solid #2196F3; color: #2196F3; margin-bottom: -2px; }
.ao-tabcontent { display: none; }
.ao-tabcontent.active { display: block; }
.ao-form td { padding: 6px 12px; }
.ao-form input[type=text] { width: 400px; padding: 4px; }
.btn-primary { background: #2196F3; color: white; border: none; padding: 8px 16px; cursor: pointer; border-radius: 4px; }
.btn-secondary { background: #777; color: white; border: none; padding: 8px 16px; cursor: pointer; border-radius: 4px; }
#results-table, #review-table { width: 100%; border-collapse: collapse; margin-top: 12px; }
#results-table th, #results-table td,
#review-table th, #review-table td { border: 1px solid #ddd; padding: 8px; text-align: left; }
#results-table thead { background: #f5f5f5; }
.error-banner { background: #f44336; color: white; padding: 12px; border-radius: 4px; }
#logs-content { background: #111; color: #eee; padding: 12px; font-size: 12px; height: 400px; overflow-y: auto; white-space: pre-wrap; }
#scan-progress { margin: 12px 0; }
progress { width: 400px; }
```

- [ ] **Step 4: Commit**

```bash
git add ui/
git commit -m "feat: PHP config page and Unraid plugin UI shell"
```

---

## Task 17: JavaScript UI Logic

**Files:**
- Create: `ui/js/app.js`

- [ ] **Step 1: Write app.js**

```javascript
// ui/js/app.js

const API = (action, opts = {}) =>
  fetch(`?action=${action}`, { method: opts.body ? 'POST' : 'GET', ...opts });

// Tab switching
document.querySelectorAll('.ao-tab').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.ao-tab, .ao-tabcontent').forEach(el => el.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
    if (btn.dataset.tab === 'review') loadReview();
    if (btn.dataset.tab === 'logs') loadLogs();
  });
});

// --- Config ---
const threshold = document.getElementById('cfg-threshold');
const thresholdVal = document.getElementById('cfg-threshold-val');
if (threshold) {
  thresholdVal.textContent = (threshold.value / 100).toFixed(2);
  threshold.addEventListener('input', () => {
    thresholdVal.textContent = (threshold.value / 100).toFixed(2);
  });
}

const sttSelect = document.getElementById('cfg-stt');
function updateSttVisibility() {
  const val = sttSelect.value;
  document.getElementById('cfg-whisper-row').style.display = val === 'local_whisper' ? '' : 'none';
  document.getElementById('cfg-apikey-row').style.display = ['openai_api', 'google_speech'].includes(val) ? '' : 'none';
}
if (sttSelect) { sttSelect.addEventListener('change', updateSttVisibility); updateSttVisibility(); }

// Pre-select saved STT value
fetch('?action=config_get').then(r => r.json()).then(cfg => {
  if (cfg.stt_engine && sttSelect) { sttSelect.value = cfg.stt_engine; updateSttVisibility(); }
  if (cfg.whisper_model) document.getElementById('cfg-whisper-model').value = cfg.whisper_model;
  if (cfg.confidence_threshold && threshold) {
    threshold.value = Math.round(cfg.confidence_threshold * 100);
    thresholdVal.textContent = cfg.confidence_threshold.toFixed(2);
  }
});

document.getElementById('cfg-save-btn')?.addEventListener('click', async () => {
  const payload = {
    source_path: document.getElementById('cfg-source').value,
    dest_path: document.getElementById('cfg-dest').value,
    google_books_api_key: document.getElementById('cfg-gbkey').value,
    stt_engine: sttSelect.value,
    whisper_model: document.getElementById('cfg-whisper-model').value,
    stt_api_key: document.getElementById('cfg-sttkey').value,
    confidence_threshold: parseFloat(threshold.value) / 100,
  };
  const r = await API('config_save', { body: JSON.stringify(payload) });
  const data = await r.json();
  document.getElementById('cfg-status').textContent = data.error ? 'Error: ' + data.error : 'Saved.';
});

// --- Scan ---
let pollInterval = null;

document.getElementById('scan-start-btn')?.addEventListener('click', async () => {
  await API('scan_start', { body: '{}' });
  startPolling();
});

document.getElementById('scan-undo-btn')?.addEventListener('click', async () => {
  if (!confirm('Undo the last scan? This will move files back to their original locations.')) return;
  const r = await API('scan_undo', { body: '{}' });
  const data = await r.json();
  alert(data.error ? 'Error: ' + data.error : `Undone ${data.reversed} file(s).`);
});

function startPolling() {
  if (pollInterval) clearInterval(pollInterval);
  pollInterval = setInterval(pollScanStatus, 2000);
  pollScanStatus();
}

async function pollScanStatus() {
  const r = await API('scan_status');
  const state = await r.json();

  const progress = document.getElementById('scan-progress');
  const results = document.getElementById('scan-results');
  const bar = document.getElementById('scan-bar');
  const current = document.getElementById('scan-current');

  if (state.status === 'scanning') {
    progress.style.display = '';
    results.style.display = 'none';
    current.textContent = state.current_book || '...';
    if (state.total_books > 0) bar.value = Math.round((state.processed_books / state.total_books) * 100);
  } else if (state.status === 'awaiting_approval') {
    clearInterval(pollInterval);
    progress.style.display = 'none';
    results.style.display = '';
    renderResults(state.proposed_moves);
  } else if (state.status === 'complete' || state.status === 'error') {
    clearInterval(pollInterval);
    progress.style.display = 'none';
    if (state.error) alert('Scan error: ' + state.error);
  }
}

function renderResults(moves) {
  const tbody = document.getElementById('results-body');
  tbody.innerHTML = '';
  moves.forEach(move => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><input type="checkbox" class="approve-cb" data-id="${move.id}" checked></td>
      <td style="font-size:12px">${move.book_group.folder}</td>
      <td style="font-size:12px">${move.proposed_path || '—'}</td>
      <td>${move.match ? Math.round(move.match.confidence * 100) + '%' : '—'}</td>
      <td>${move.match ? move.match.source : '—'}</td>
    `;
    tbody.appendChild(tr);
  });
}

document.getElementById('apply-btn')?.addEventListener('click', async () => {
  const approved_ids = [...document.querySelectorAll('.approve-cb:checked')].map(cb => cb.dataset.id);
  const write_tags = document.getElementById('write-tags-toggle').checked;
  const r = await API('scan_approve', { body: JSON.stringify({ approved_ids, write_tags }) });
  const data = await r.json();
  if (data.error) { alert('Error: ' + data.error); return; }
  alert(`Done. Moved: ${data.moved}. Errors: ${(data.errors || []).length}`);
  document.getElementById('scan-results').style.display = 'none';
});

// --- Manual Review ---
async function loadReview() {
  const r = await API('manual_review');
  const items = await r.json();
  const tbody = document.getElementById('review-body');
  tbody.innerHTML = '';
  if (!items.length) { tbody.innerHTML = '<tr><td colspan="3">No items pending review.</td></tr>'; return; }
  items.forEach(item => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${item.book_group.folder}</td>
      <td>${item.book_group.files.length} file(s)</td>
      <td><button onclick="moveUnidentified('${item.id}')">Move to _unidentified</button></td>
    `;
    tbody.appendChild(tr);
  });
}

async function moveUnidentified(id) {
  if (!confirm('Move this book to _unidentified folder?')) return;
  const r = await fetch(`?action=move_unidentified&id=${id}`, { method: 'POST', body: '{}' });
  const data = await r.json();
  if (data.error) { alert('Error: ' + data.error); return; }
  loadReview();
}

// --- Logs ---
async function loadLogs() {
  const r = await API('logs');
  const data = await r.json();
  document.getElementById('logs-content').textContent = (data.lines || []).join('\n');
}
document.getElementById('logs-refresh-btn')?.addEventListener('click', loadLogs);
```

- [ ] **Step 2: Verify no JS syntax errors**

```bash
node --check ui/js/app.js
```
Expected: No output (no errors)

- [ ] **Step 3: Commit**

```bash
git add ui/js/app.js
git commit -m "feat: JavaScript UI for scan, approval, review, and logs"
```

---

## Task 18: Unraid Plugin Packaging

**Files:**
- Create: `plugin/audiobook-organizer.plg`
- Create: `plugin/scripts/rc.audiobook-organizer`
- Create: `plugin/scripts/install.sh`
- Create: `plugin/scripts/uninstall.sh`

Note: Unraid `.plg` files are XML. The plugin system fetches and installs `.txz` packages. For development, files are installed directly. The rc.d script manages the daemon service.

- [ ] **Step 1: Write rc.audiobook-organizer**

```bash
#!/bin/bash
# plugin/scripts/rc.audiobook-organizer

PLUGIN_DIR=/usr/local/emhttp/plugins/audiobook-organizer
DAEMON_DIR=/usr/local/lib/audiobook-organizer-daemon
VENV_PYTHON=$DAEMON_DIR/venv/bin/python
LOG_DIR=/boot/config/plugins/audiobook-organizer
PID_FILE=/var/run/audiobook-organizer.pid

mkdir -p $LOG_DIR

start() {
  if [ -f $PID_FILE ] && kill -0 $(cat $PID_FILE) 2>/dev/null; then
    echo "Audiobook Organizer already running (pid $(cat $PID_FILE))"
    return
  fi
  DB_PATH=$LOG_DIR/state.db \
  $VENV_PYTHON -m uvicorn main:app \
    --host 127.0.0.1 --port 7171 \
    --log-level warning \
    --app-dir $DAEMON_DIR \
    >> $LOG_DIR/daemon.log 2>&1 &
  echo $! > $PID_FILE
  echo "Audiobook Organizer started (pid $(cat $PID_FILE))"
}

stop() {
  if [ -f $PID_FILE ]; then
    kill $(cat $PID_FILE) 2>/dev/null
    rm -f $PID_FILE
    echo "Audiobook Organizer stopped"
  fi
}

restart() { stop; sleep 1; start; }
status() {
  if [ -f $PID_FILE ] && kill -0 $(cat $PID_FILE) 2>/dev/null; then
    echo "Running (pid $(cat $PID_FILE))"
  else
    echo "Not running"
  fi
}

case "$1" in start|stop|restart|status) $1 ;; *) echo "Usage: $0 {start|stop|restart|status}" ;; esac
```

- [ ] **Step 2: Write install.sh**

```bash
#!/bin/bash
# plugin/scripts/install.sh

set -e
DAEMON_DIR=/usr/local/lib/audiobook-organizer-daemon
PLUGIN_UI_DIR=/usr/local/emhttp/plugins/audiobook-organizer

echo "Installing Audiobook Organizer..."

# Copy daemon files
mkdir -p $DAEMON_DIR
cp -r daemon/* $DAEMON_DIR/

# Create Python venv and install deps
python3 -m venv $DAEMON_DIR/venv
$DAEMON_DIR/venv/bin/pip install --quiet -r $DAEMON_DIR/requirements.txt

# Copy UI files
mkdir -p $PLUGIN_UI_DIR
cp -r ui/* $PLUGIN_UI_DIR/

# Copy rc script
cp plugin/scripts/rc.audiobook-organizer /etc/rc.d/rc.audiobook-organizer
chmod +x /etc/rc.d/rc.audiobook-organizer

# Start daemon
/etc/rc.d/rc.audiobook-organizer start

echo "Installation complete. Visit Tools > Audiobook Organizer in Unraid."
```

- [ ] **Step 3: Write uninstall.sh**

```bash
#!/bin/bash
# plugin/scripts/uninstall.sh

/etc/rc.d/rc.audiobook-organizer stop 2>/dev/null || true
rm -rf /usr/local/lib/audiobook-organizer-daemon
rm -rf /usr/local/emhttp/plugins/audiobook-organizer
rm -f /etc/rc.d/rc.audiobook-organizer
echo "Audiobook Organizer removed. Config preserved at /boot/config/plugins/audiobook-organizer/"
```

- [ ] **Step 4: Write audiobook-organizer.plg**

```xml
<?xml version='1.0' standalone='yes'?>
<!DOCTYPE PLUGIN [
  <!ENTITY name "audiobook-organizer">
  <!ENTITY author "your-github-username">
  <!ENTITY version "1.0.0">
  <!ENTITY pluginURL "https://raw.githubusercontent.com/your-github-username/audiobook-organizer/main/plugin/audiobook-organizer.plg">
]>
<PLUGIN name="&name;" author="&author;" version="&version;" pluginURL="&pluginURL;">

<CHANGES>
  <VERSION num="1.0.0">
    Initial release. Multi-stage audiobook identification and organization.
  </VERSION>
</CHANGES>

<FILE Name="/boot/config/plugins/&name;/install.sh" Run="bash">
<INLINE>
#!/bin/bash
# Inline install script — fetches and runs install.sh from repo
# In production, replace with actual txz package fetch + install
bash /boot/config/plugins/audiobook-organizer/install.sh
</INLINE>
</FILE>

<FILE Name="/boot/config/plugins/&name;/uninstall.sh">
<INLINE>
#!/bin/bash
bash /usr/local/emhttp/plugins/audiobook-organizer/../../../lib/audiobook-organizer-daemon/../../../scripts/uninstall.sh
</INLINE>
</FILE>

</PLUGIN>
```

- [ ] **Step 5: Make scripts executable**

```bash
chmod +x plugin/scripts/rc.audiobook-organizer plugin/scripts/install.sh plugin/scripts/uninstall.sh
```

- [ ] **Step 6: Commit**

```bash
git add plugin/
git commit -m "feat: Unraid plugin packaging, rc.d service script, install/uninstall"
```

---

## Task 19: Integration Test

**Files:**
- Create: `daemon/tests/test_integration.py`

This test exercises the full pipeline end-to-end using mocked Google Books and real file operations on tmp directories.

- [ ] **Step 1: Write integration test**

```python
# daemon/tests/test_integration.py
import pytest
import os
os.environ["DB_PATH"] = "/tmp/test-ao-integration.db"

from pathlib import Path
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from main import app
from tests.conftest import make_fake_mp3
from mutagen.id3 import ID3, TIT2, TPE1

HOBBIT_CANDIDATE = {
    "id": "abc123",
    "volumeInfo": {
        "title": "The Hobbit",
        "authors": ["J.R.R. Tolkien"],
        "publishedDate": "1937",
        "seriesInfo": None,
    }
}

@pytest.fixture(autouse=True)
async def reset():
    from db import init_db
    await init_db()
    yield

@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

@pytest.mark.asyncio
async def test_full_pipeline_scan_approve_move(client, tmp_path):
    # Setup: tagged MP3 in source dir
    src = tmp_path / "source"
    dest = tmp_path / "dest"
    src.mkdir(); dest.mkdir()

    audio = src / "thehobbit.mp3"
    make_fake_mp3(audio)
    tags = ID3()
    tags.add(TIT2(encoding=3, text="The Hobbit"))
    tags.add(TPE1(encoding=3, text="J.R.R. Tolkien"))
    tags.save(str(audio))

    # Save config
    await client.post("/api/config", json={
        "source_path": str(src),
        "dest_path": str(dest),
        "google_books_api_key": "test-key",
        "stt_engine": "none",
        "whisper_model": "small",
        "stt_api_key": "",
        "confidence_threshold": 0.80,
    })

    # Start scan with mocked Google Books
    with patch("pipeline.google_books.httpx.AsyncClient") as mock_client:
        mock_resp = AsyncMock()
        mock_resp.json.return_value = {"items": [HOBBIT_CANDIDATE]}
        mock_resp.raise_for_status = AsyncMock()
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)

        await client.post("/api/scan/start")

        # Wait for scan to complete (background task runs inline in test)
        import asyncio
        for _ in range(20):
            r = await client.get("/api/scan/status")
            state = r.json()
            if state["status"] in ("awaiting_approval", "error"):
                break
            await asyncio.sleep(0.1)

    assert state["status"] == "awaiting_approval"
    assert len(state["proposed_moves"]) == 1
    move = state["proposed_moves"][0]
    assert "Hobbit" in move["proposed_path"]

    # Approve the move
    r = await client.post("/api/scan/approve", json={
        "approved_ids": [move["id"]],
        "write_tags": False,
    })
    result = r.json()
    assert result["moved"] == 1

    # Verify file moved to correct location
    expected = dest / "J.R.R. Tolkien" / "The Hobbit" / "thehobbit.mp3"
    assert expected.exists(), f"Expected file at {expected}"
    assert not audio.exists(), "Source file should be gone"
```

- [ ] **Step 2: Run integration test**

```bash
DB_PATH=/tmp/test-ao-integration.db pytest tests/test_integration.py -v
```
Expected: PASS

- [ ] **Step 3: Run full test suite**

```bash
DB_PATH=/tmp/test-ao-final.db pytest tests/ -v
```
Expected: All tests PASS, no failures

- [ ] **Step 4: Final commit**

```bash
git add daemon/tests/test_integration.py
git commit -m "test: end-to-end integration test for full scan/approve/move pipeline"
```

---

## Appendix: Manual Testing on Unraid

After packaging:

1. SSH into Unraid: `ssh root@unraid`
2. Run install: `bash /path/to/install.sh`
3. Verify daemon: `curl http://localhost:7171/api/health`
4. Open Unraid UI → Tools → Audiobook Organizer
5. Configure source/dest paths and Google Books API key
6. Click "Start Scan" — watch progress
7. Review proposed moves, uncheck any to skip
8. Click "Apply Selected"
9. Verify files in dest directory have correct structure

**Google Books API Key:** Get free key at https://console.developers.google.com → enable "Books API" → create credentials.

**Whisper on CPU:** `small` model transcribes ~1 min of audio per minute on modern CPU. 10-minute chunk = ~10 min wait per unidentified book. Use `tiny` for speed, `medium` for accuracy.
