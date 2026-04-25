# daemon/tests/test_integration.py
import pytest
import asyncio
from pathlib import Path
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from main import app
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

@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

@pytest.mark.asyncio
async def test_full_pipeline_scan_approve_move(client, tmp_path):
    src = tmp_path / "source"
    dest = tmp_path / "dest"
    src.mkdir(); dest.mkdir()

    audio = src / "thehobbit.mp3"
    tags = ID3()
    tags.add(TIT2(encoding=3, text="The Hobbit"))
    tags.add(TPE1(encoding=3, text="J.R.R. Tolkien"))
    tags.save(str(audio))

    await client.post("/api/config", json={
        "source_path": str(src),
        "dest_path": str(dest),
        "google_books_api_key": "test-key",
        "stt_engine": "none",
        "whisper_model": "small",
        "stt_api_key": "",
        "confidence_threshold": 0.80,
    })

    with patch("identifier.query_google_books", AsyncMock(return_value=[HOBBIT_CANDIDATE])):
        await client.post("/api/scan/start")

        state = None
        for _ in range(50):
            r = await client.get("/api/scan/status")
            state = r.json()
            if state["status"] in ("awaiting_approval", "error"):
                break
            await asyncio.sleep(0.2)

    assert state["status"] == "awaiting_approval", f"Got status: {state['status']}, error: {state.get('error')}"
    assert len(state["proposed_moves"]) == 1
    move = state["proposed_moves"][0]
    assert "Hobbit" in move["proposed_path"]

    r = await client.post("/api/scan/approve", json={
        "approved_ids": [move["id"]],
        "write_tags": False,
    })
    result = r.json()
    assert result["moved"] == 1

    expected = dest / "J.R.R. Tolkien" / "The Hobbit" / "thehobbit.mp3"
    assert expected.exists(), f"Expected file at {expected}"
    assert not audio.exists(), "Source file should be gone"
