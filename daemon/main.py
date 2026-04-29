# daemon/main.py
import json
import logging
import os
import aiosqlite
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, BackgroundTasks, HTTPException, Query
from typing import Optional
from db import init_db, _db_path
from config import load_config, save_config
from models import Config, ApproveRequest, MoveFileRequest, ScanStatus
from scan_worker import load_scan_state, save_scan_state, run_scan, request_cancel
from pipeline.google_books import query_google_books
from pipeline.open_library import lookup_series
from path_builder import build_proposed_path
from file_mover import move_book_files, move_single_file, move_remaining_folder_contents, delete_empty_source_dirs, undo_moves, MoveRecord
from tag_writer import write_tags_to_files

_log_path = "/config/audiobook-organizer.log"
_ao_logger = logging.getLogger("ao")
_ao_logger.setLevel(logging.INFO)
import os as _os
if _os.path.isdir(_os.path.dirname(_log_path)):
    _fh = logging.FileHandler(_log_path)
    _fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    _ao_logger.addHandler(_fh)

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

@app.post("/api/scan/cancel")
async def cancel_scan():
    state = await load_scan_state()
    if state.status != ScanStatus.SCANNING:
        raise HTTPException(409, "No scan in progress")
    request_cancel()
    return {"message": "Cancel requested"}

@app.post("/api/scan/move-file")
async def move_one_file(req: MoveFileRequest):
    state = await load_scan_state()
    move = next((m for m in state.proposed_moves if m.id == req.move_id), None)
    if not move:
        raise HTTPException(404, "Move not found")
    if req.file_path not in move.book_group.files:
        raise HTTPException(400, "File not in move")
    if not move.proposed_path:
        raise HTTPException(400, "No proposed path set")
    _ao_logger.info("MOVE_REQ file=%r cleanup=%s folder=%r proposed=%r files_in_group=%d",
                    req.file_path, req.cleanup, move.book_group.folder,
                    move.proposed_path, len(move.book_group.files))
    try:
        record = move_single_file(req.file_path, move.proposed_path)
        if req.cleanup:
            move_remaining_folder_contents(move.book_group.folder, move.proposed_path)
            remaining = [f for f in move.book_group.files if f != req.file_path]
            delete_empty_source_dirs([req.file_path] + remaining)
        return {"src": record.src, "dst": record.dst}
    except Exception as e:
        _ao_logger.error("MOVE_ERR file=%r error=%r", req.file_path, str(e))
        raise HTTPException(500, str(e))


@app.post("/api/scan/approve")
async def approve_moves(req: ApproveRequest):
    if not req.approved_ids:
        return {"moved": 0, "errors": []}

    state = await load_scan_state()
    if state.status not in (ScanStatus.AWAITING_APPROVAL, ScanStatus.COMPLETE):
        raise HTTPException(400, "No scan awaiting approval")

    approved = [m for m in state.proposed_moves if m.id in req.approved_ids]
    all_records: list[MoveRecord] = []

    state.status = ScanStatus.MOVING
    await save_scan_state(state)

    errors = []
    for move in approved:
        try:
            if req.already_moved:
                # Files already moved individually; just write tags and record as moved
                records = [MoveRecord(src=f, dst=str(Path(move.proposed_path) / Path(f).name))
                           for f in move.book_group.files]
            else:
                records = move_book_files(move.book_group.files, move.proposed_path)
            all_records.extend(records)
            if req.write_tags and move.match:
                write_tags_to_files([r.dst for r in records], move.match)
            move.status = "moved"
        except Exception as e:
            move.status = "failed"
            errors.append(str(e))

    if all_records:
        async with aiosqlite.connect(_db_path()) as db:
            await db.execute(
                "INSERT INTO rollback_log (moves, created_at) VALUES (?, ?)",
                (json.dumps([{"src": r.src, "dst": r.dst} for r in all_records]),
                 datetime.utcnow().isoformat())
            )
            await db.commit()

    state.status = ScanStatus.COMPLETE if not errors else ScanStatus.ERROR
    if errors:
        state.error = f"{len(errors)} move(s) failed"
    await save_scan_state(state)
    return {"moved": len([m for m in approved if m.status == "moved"]), "errors": errors}

@app.post("/api/scan/undo")
async def undo_last_scan():
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
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

@app.get("/api/manual-review")
async def get_manual_review():
    state = await load_scan_state()
    return state.manual_review


@app.post("/api/manual-review/{item_id}/identify")
async def identify_manual(item_id: str, body: dict):
    state = await load_scan_state()
    item = next((m for m in state.manual_review if m.id == item_id), None)
    if not item:
        raise HTTPException(404, "Item not found")
    cfg = await load_config()
    from models import BookMatch, IdentificationSource
    match = BookMatch(
        title=body.get("title", "Unknown"),
        author=body.get("author", "Unknown"),
        series=body.get("series") or None,
        series_number=float(body["series_number"]) if body.get("series_number") else None,
        confidence=1.0,
        source=IdentificationSource.UNIDENTIFIED,
    )
    proposed_path = build_proposed_path(match, cfg.dest_path)
    from models import ProposedMove
    item.match = match
    item.proposed_path = proposed_path
    item.approved = True
    item.status = "pending"
    state.manual_review = [m for m in state.manual_review if m.id != item_id]
    state.proposed_moves.append(item)
    await save_scan_state(state)
    return {"proposed_path": proposed_path}

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

@app.get("/api/browse")
async def browse(path: str = Query(default="/mnt")):
    try:
        p = Path(path).resolve()
        entries = sorted(
            [{"name": e.name, "path": str(e)} for e in p.iterdir() if e.is_dir() and not e.name.startswith('.')],
            key=lambda x: x["name"].lower()
        )
        return {"path": str(p), "parent": str(p.parent), "entries": entries}
    except PermissionError:
        raise HTTPException(403, "Permission denied")
    except FileNotFoundError:
        raise HTTPException(404, "Path not found")

@app.post("/api/manual-review/{item_id}/transcribe")
async def transcribe_item(item_id: str):
    state = await load_scan_state()
    item = next((m for m in state.manual_review if m.id == item_id), None)
    if not item:
        return {"error": "Item not found"}
    cfg = await load_config()
    engine_val = cfg.stt_engine.value if hasattr(cfg.stt_engine, 'value') else str(cfg.stt_engine)
    if engine_val == "none":
        return {"error": "No STT engine configured — set one in Configuration tab"}
    if not item.book_group.files:
        return {"error": "No files in book group"}
    import asyncio
    transcript = await asyncio.to_thread(_transcribe_first_minute, item.book_group.files[0], cfg)
    return {"transcript": transcript}

def _transcribe_first_minute(first_file: str, cfg) -> str:
    import os
    tmp_wav = None
    try:
        from stt.local_whisper import extract_audio_chunk
        tmp_wav = extract_audio_chunk(first_file, 60)
        engine = cfg.stt_engine.value if hasattr(cfg.stt_engine, 'value') else str(cfg.stt_engine)
        model = cfg.whisper_model.value if hasattr(cfg.whisper_model, 'value') else str(cfg.whisper_model)
        if engine == "local_whisper":
            from stt.local_whisper import transcribe_local
            return transcribe_local(tmp_wav, model) or ""
        elif engine == "openai":
            from stt.openai_stt import transcribe_openai
            return transcribe_openai(tmp_wav, cfg.stt_api_key) or ""
        elif engine == "google":
            from stt.google_stt import transcribe_google_sync
            return transcribe_google_sync(tmp_wav, cfg.stt_api_key) or ""
        return f"Error: unknown engine {engine!r}"
    except Exception as e:
        return f"Error: {e}"
    finally:
        if tmp_wav and os.path.exists(tmp_wav):
            os.unlink(tmp_wav)

@app.get("/api/logs")
async def get_logs():
    import os
    log_path = "/config/audiobook-organizer.log"
    if not os.path.exists(log_path):
        return {"lines": []}
    with open(log_path) as f:
        lines = f.readlines()[-200:]
    return {"lines": [l.rstrip() for l in lines]}
