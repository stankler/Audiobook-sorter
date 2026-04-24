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
