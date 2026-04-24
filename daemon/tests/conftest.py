import os
import pytest
from pathlib import Path

# Set test DB path before any module-level code in test files can import db.py
os.environ.setdefault("DB_PATH", "/tmp/test-audiobook-organizer.db")

@pytest.fixture
def tmp_dir(tmp_path):
    yield tmp_path

@pytest.fixture
def audio_dir(tmp_path):
    d = tmp_path / "audiobooks"
    d.mkdir()
    return d

def make_fake_mp3(path: Path, content: bytes = b"ID3" + b"\x00" * 100):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path

@pytest.fixture(autouse=True)
async def clean_db():
    db_path = os.environ["DB_PATH"]
    if os.path.exists(db_path):
        os.remove(db_path)
    from db import init_db
    await init_db()
    yield
    if os.path.exists(db_path):
        os.remove(db_path)
