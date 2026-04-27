# daemon/scan_worker.py
import json
import asyncio
import logging
import uuid
from datetime import datetime
import aiosqlite
from models import ScanState, ScanStatus, ProposedMove, Config
from scanner import scan_for_books
from identifier import identify_book
from db import _db_path

logger = logging.getLogger("ao")

_cancel_event = asyncio.Event()

def request_cancel():
    _cancel_event.set()

async def load_scan_state() -> ScanState:
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT data FROM scan_state WHERE id = 1")
        row = await cursor.fetchone()
        if row:
            return ScanState.model_validate_json(row["data"])
    return ScanState()

async def save_scan_state(state: ScanState):
    async with aiosqlite.connect(_db_path()) as db:
        await db.execute(
            "INSERT OR REPLACE INTO scan_state (id, status, data) VALUES (1, ?, ?)",
            (state.status.value, state.model_dump_json()),
        )
        await db.commit()

async def run_scan(cfg: Config):
    _cancel_event.clear()
    state = ScanState(status=ScanStatus.SCANNING, started_at=datetime.utcnow())
    await save_scan_state(state)

    try:
        groups = scan_for_books(cfg.source_path)
        state.total_books = len(groups)
        await save_scan_state(state)

        for group in groups:
            if _cancel_event.is_set():
                logger.info("SCAN_CANCELLED")
                state.status = ScanStatus.CANCELLED
                state.completed_at = datetime.utcnow()
                await save_scan_state(state)
                return

            state.current_book = group.folder
            state.processed_books += 1
            await save_scan_state(state)

            candidates = await identify_book(group, cfg)
            move_id = str(uuid.uuid4())
            logger.info("BOOK folder=%r  candidates=%d", group.folder, len(candidates))
            state.manual_review.append(ProposedMove(
                id=move_id, book_group=group,
                candidates=candidates, match=None, proposed_path=None, approved=False,
            ))

        state.status = ScanStatus.COMPLETE
        state.completed_at = datetime.utcnow()
    except Exception as e:
        state.status = ScanStatus.ERROR
        state.error = str(e)

    await save_scan_state(state)
