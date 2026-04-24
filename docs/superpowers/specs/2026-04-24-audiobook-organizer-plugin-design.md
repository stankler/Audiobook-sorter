# Audiobook Organizer — Unraid Plugin Design

**Date:** 2026-04-24  
**Status:** Approved

---

## Overview

Unraid plugin that scans a directory of chaotic audiobook files, identifies each book using a multi-stage pipeline (metadata tags → filename parsing → Google Books API → speech-to-text), proposes a sorted folder structure, and moves files only after user approval via the Unraid web UI.

---

## Architecture

```
┌─────────────────────────────────┐
│       Unraid Web UI             │
│  PHP + vanilla JS               │
│  - Config page                  │
│  - Scan trigger                 │
│  - Results table (approve/skip) │
│  - Manual review queue          │
│  - Logs tab                     │
│  - Undo last scan               │
└────────────┬────────────────────┘
             │ HTTP (localhost:7171)
             ▼
┌─────────────────────────────────┐
│     Python Daemon (FastAPI)     │
│  - Scan worker                  │
│  - Identification pipeline      │
│  - STT engine (Whisper/cloud)   │
│  - File mover + rollback        │
│  - SQLite state DB              │
└─────────────────────────────────┘
```

- PHP/JS frontend communicates with Python daemon over local HTTP on port 7171
- Daemon persists scan state in SQLite — survives page refresh and browser close
- Plugin ships as standard Unraid `.plg` package containing Python venv, FastAPI daemon, and PHP UI files
- Daemon runs as a background service managed by Unraid's rc.d system

---

## Identification Pipeline

Files in the same folder with sequential naming are grouped as one book. Lone files are treated as standalone books. Ambiguous groupings are flagged for manual review.

Each book passes through stages in order, stopping at first confident match:

### Stage 1 — ID3 / Metadata Tags
- Read tags using `mutagen`
- Extract title + author
- Query Google Books API
- Confidence ≥ threshold → **MATCH**

### Stage 2 — Filename / Folder Name Parsing
- Strip track numbers, brackets, narrator credits, file extensions
- Extract title candidate
- Query Google Books API
- Confidence ≥ threshold → **MATCH**

### Stage 3 — Speech-to-Text
- Transcribe first 10 minutes of first audio file in book
- Scan transcript for title patterns: `"this is [title] by [author]"`, title appearing 2+ times
- Query Google Books API with extracted candidates
- Confidence ≥ threshold → **MATCH**

### Stage 4 — No Match
- Book flagged → added to manual review queue
- Files remain in original location until user takes action from manual review queue
- User can manually assign book identity in review queue, then trigger a move to `{dest}/_unidentified/` or a specified path

### Confidence Score
Weighted combination of: title string similarity, author match, publication year plausibility. Default threshold: 0.85 (configurable 0.70–0.95).

When Google Books returns ambiguous results below threshold: skip, flag for manual review. No auto-guessing.

---

## Folder Structure

```
{library_root}/
  {Author Last, First}/
    {Series Name}/{Series #} - {Book Title}/
      {original files}
    {Standalone Title}/
      {original files}
```

**Examples:**
```
Sanderson, Brandon/
  Stormlight Archive/
    1 - The Way of Kings/
      01-the-way-of-kings.mp3
    2 - Words of Radiance/
      words-of-radiance.m4b
  Elantris/
    elantris.m4b

King, Stephen/
  The Shining/
    the-shining.mp3
```

- Original filenames preserved inside destination folder
- Series number prepended to book folder when series data available from Google Books

---

## File Moving

- Dry-run always executes first; actual moves only after explicit user approval
- Moves are atomic: copy → checksum verify → delete source
- Rollback log (`rollback.json`) written to dest root before any move batch
- "Undo Last Scan" button replays moves in reverse; available until next scan runs
- Destination conflict (path already exists) → flag, never overwrite

---

## Approval UI Flow

1. Scan completes → results table populates
2. Each row shows: current path → proposed path, confidence %, identification source (tags / filename / STT)
3. All rows checked by default; user unchecks to skip individual books
4. "Write tags after move" checkbox shown above table — applies to entire approval batch
5. "Apply Selected" button → daemon executes approved moves, shows progress
6. Manual review queue tab shows flagged books separately (low confidence + unidentified); files remain in place until user acts

---

## Configuration

| Field | Description |
|-------|-------------|
| Library source path | Directory to scan |
| Library destination path | Root of organized library |
| Google Books API key | Required for API lookups |
| STT engine | None / Local Whisper / OpenAI API / Google Speech |
| Whisper model size | tiny / base / small / medium / large (if local) |
| STT API key | Required if cloud STT selected |
| Confidence threshold | Slider 0.70–0.95, default 0.85 |

---

## STT Engines

### Local — OpenAI Whisper
- Ships `openai-whisper` in bundled Python venv
- Transcribes first 10 min of first audio file per book
- Runs on CPU by default; auto-detects NVIDIA GPU via `torch.cuda`
- Model size tradeoffs shown in UI (tiny = fast/less accurate, large = slow/best)

### Cloud — OpenAI Whisper API
- Sends first 10 min of audio to OpenAI
- Estimated cost displayed in UI before STT stage runs (~$0.006/min)
- Requires OpenAI API key

### Cloud — Google Speech-to-Text
- Same 10-min limit and cost warning
- Requires Google Cloud API key

---

## Google Books API

- User-provided API key
- Rate limited to 1 request/second (respects free tier: 1000 req/day)
- Query results cached in SQLite by query hash — same search never repeated
- Plugin functional without API key: stages 1–3 still extract candidates, placed in manual review queue instead of auto-matched

---

## Tag Writing

When "Write tags after move" is checked in the approval UI:
- `mutagen` updates title, author, album artist, and series tags on moved files
- Applied after successful move, before scan marked complete
- Only updates files whose book was positively identified (not manual review items)
- Decision is per-approval-batch, not persisted in config

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Google Books API down | Skip to STT stage, log warning |
| STT fails (corrupt/unsupported codec) | Flag book for manual review, continue scan |
| Disk full during move | Abort remaining moves, rollback completed moves, alert UI |
| Permission denied on file | Flag individual file, continue |
| Destination path already exists | Flag conflict, never overwrite |
| Same book in multiple formats | Flag for user, don't auto-pick |

---

## Edge Cases

- **Multi-disc / split books** (Part 1, Part 2): grouped as one book, numbered subfolder
- **Anthologies / short story collections**: matched as standalone (no series)
- **Unidentified after all 4 stages**: files stay in place, shown in manual review queue; user can assign identity or explicitly move to `{dest}/_unidentified/`
- **Nested chaos** (folders within folders): recursive scan, each file group evaluated independently
- **Duplicate formats** (mp3 + m4b of same book): flagged, user decides

---

## Logging

- All decisions logged: identification source, confidence score, proposed path, outcome
- Log viewable in plugin UI under "Logs" tab
- Written to `/boot/config/plugins/audiobook-organizer/audiobook-organizer.log`

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| UI | PHP + vanilla JS |
| Daemon | Python 3.11, FastAPI |
| Tag read/write | mutagen |
| Local STT | openai-whisper + torch |
| Audio decoding | ffmpeg (system) |
| State / cache | SQLite (aiosqlite) |
| Book lookup | Google Books API v1 |
| HTTP client | httpx |
| Plugin packaging | Unraid .plg format |
