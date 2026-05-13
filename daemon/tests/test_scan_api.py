# daemon/tests/test_scan_api.py
import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from main import app

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
async def test_start_scan_returns_accepted(client):
    from models import Config
    with patch("main.run_scan", AsyncMock()), \
         patch("main.load_config", AsyncMock(return_value=Config(
             source_path="/mnt/src", dest_path="/mnt/dest"
         ))):
        r = await client.post("/api/scan/start")
    assert r.status_code == 202

@pytest.mark.asyncio
async def test_approve_empty_list_returns_ok(client):
    r = await client.post("/api/scan/approve", json={"approved_ids": [], "write_tags": False})
    assert r.status_code == 200

@pytest.mark.asyncio
async def test_get_manual_review_empty(client):
    r = await client.get("/api/manual-review")
    assert r.status_code == 200
    assert r.json() == []

@pytest.mark.asyncio
async def test_move_to_unidentified_returns_404_when_no_such_id(client):
    r = await client.post("/api/manual-review/nonexistent/move-unidentified")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_move_to_unidentified_moves_files_and_removes_item(client, tmp_path):
    from models import Config, ScanState, ProposedMove, BookGroup
    from scan_worker import save_scan_state

    src_folder = tmp_path / "src" / "Book One"
    src_folder.mkdir(parents=True)
    f1 = src_folder / "disc01.mp3"
    f1.write_bytes(b"ID3" + b"\x00" * 100)
    f2 = src_folder / "cover.jpg"
    f2.write_bytes(b"JPG")

    dest_root = tmp_path / "dest"
    dest_root.mkdir()

    state = ScanState()
    state.manual_review.append(ProposedMove(
        id="abc123",
        book_group=BookGroup(files=[str(f1), str(f2)], folder=str(src_folder)),
        candidates=[],
    ))
    await save_scan_state(state)

    with patch("main.load_config", AsyncMock(return_value=Config(
        source_path=str(tmp_path / "src"), dest_path=str(dest_root)
    ))):
        r = await client.post("/api/manual-review/abc123/move-unidentified")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["moved"] == 2
    assert not f1.exists() and not f2.exists()
    assert (dest_root / "_unidentified" / "Book One" / "disc01.mp3").exists()
    assert (dest_root / "_unidentified" / "Book One" / "cover.jpg").exists()

    r2 = await client.get("/api/manual-review")
    assert r2.json() == []


@pytest.mark.asyncio
async def test_move_to_unidentified_namespaces_avoids_collision(client, tmp_path):
    from models import Config, ScanState, ProposedMove, BookGroup
    from scan_worker import save_scan_state

    a_folder = tmp_path / "src" / "Book A"
    b_folder = tmp_path / "src" / "Book B"
    a_folder.mkdir(parents=True)
    b_folder.mkdir(parents=True)
    a_file = a_folder / "disc01.mp3"
    b_file = b_folder / "disc01.mp3"
    a_file.write_bytes(b"A")
    b_file.write_bytes(b"B")

    dest_root = tmp_path / "dest"
    dest_root.mkdir()

    state = ScanState()
    state.manual_review.append(ProposedMove(
        id="a", book_group=BookGroup(files=[str(a_file)], folder=str(a_folder)), candidates=[]))
    state.manual_review.append(ProposedMove(
        id="b", book_group=BookGroup(files=[str(b_file)], folder=str(b_folder)), candidates=[]))
    await save_scan_state(state)

    with patch("main.load_config", AsyncMock(return_value=Config(
        source_path=str(tmp_path / "src"), dest_path=str(dest_root)
    ))):
        r1 = await client.post("/api/manual-review/a/move-unidentified")
        r2 = await client.post("/api/manual-review/b/move-unidentified")

    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text
    assert (dest_root / "_unidentified" / "Book A" / "disc01.mp3").read_bytes() == b"A"
    assert (dest_root / "_unidentified" / "Book B" / "disc01.mp3").read_bytes() == b"B"
