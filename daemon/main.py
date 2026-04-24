# daemon/main.py
import json
import aiosqlite
from datetime import datetime
from fastapi import FastAPI, BackgroundTasks, HTTPException
from db import init_db, _db_path
from config import load_config, save_config
from models import Config, ApproveRequest, ScanStatus
from scan_worker import load_scan_state, save_scan_state, run_scan
from file_mover import move_book_files, undo_moves, MoveRecord
from tag_writer import write_tags_to_files

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
    # Allow empty approve lists without status check (no-op)
    if not req.approved_ids:
        return {"moved": 0, "errors": []}

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

    state.status = ScanStatus.COMPLETE
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
