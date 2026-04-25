import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from pipeline.google_books import query_google_books, BOOKS_API_URL

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
        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_RESPONSE
        mock_resp.raise_for_status.return_value = None
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
        results = await query_google_books("The Hobbit", "Tolkien", api_key="fake")
    assert len(results) == 1
    assert results[0]["volumeInfo"]["title"] == "The Hobbit"

@pytest.mark.asyncio
async def test_caches_result():
    with patch("pipeline.google_books.httpx.AsyncClient") as mock_client:
        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_RESPONSE
        mock_resp.raise_for_status.return_value = None
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
