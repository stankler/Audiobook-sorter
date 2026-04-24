import pytest
from pathlib import Path

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
