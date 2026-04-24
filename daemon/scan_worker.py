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
from path_builder import build_proposed_path
from db import _db_path

logger = logging.getLogger("ao")

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
