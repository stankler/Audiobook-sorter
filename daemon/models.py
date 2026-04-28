from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional, List
from datetime import datetime

class STTEngine(str, Enum):
    NONE = "none"
    LOCAL_WHISPER = "local_whisper"
    OPENAI_API = "openai_api"
    GOOGLE_SPEECH = "google_speech"

class WhisperModel(str, Enum):
    TINY = "tiny"
    BASE = "base"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"

class IdentificationSource(str, Enum):
    TAGS = "tags"
    FILENAME = "filename"
    OPEN_LIBRARY = "open_library"
    STT = "stt"
    CLAUDE = "claude"
    UNIDENTIFIED = "unidentified"

class Config(BaseModel):
    source_path: str = ""
    dest_path: str = ""
    google_books_api_key: str = ""
    anthropic_api_key: str = ""
    stt_engine: STTEngine = STTEngine.NONE
    whisper_model: WhisperModel = WhisperModel.SMALL
    stt_api_key: str = ""
    confidence_threshold: float = Field(default=0.85, ge=0.70, le=0.95)

class BookGroup(BaseModel):
    files: List[str]
    folder: str

class BookMatch(BaseModel):
    title: str
    author: str
    series: Optional[str] = None
    series_number: Optional[float] = None
    google_books_id: Optional[str] = None
    confidence: float
    source: IdentificationSource

class Candidate(BaseModel):
    title: str
    author: str
    series: Optional[str] = None
    series_number: Optional[float] = None
    source: str = ""
    confidence: float = 0.0

class ProposedMove(BaseModel):
    id: str
    book_group: BookGroup
    match: Optional[BookMatch] = None
    proposed_path: Optional[str] = None
    approved: bool = True
    status: str = "pending"
    candidates: List[Candidate] = []

class ScanStatus(str, Enum):
    IDLE = "idle"
    SCANNING = "scanning"
    AWAITING_APPROVAL = "awaiting_approval"
    MOVING = "moving"
    COMPLETE = "complete"
    CANCELLED = "cancelled"
    ERROR = "error"

class ScanState(BaseModel):
    status: ScanStatus = ScanStatus.IDLE
    total_books: int = 0
    processed_books: int = 0
    current_book: Optional[str] = None
    proposed_moves: List[ProposedMove] = []
    manual_review: List[ProposedMove] = []
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

class ApproveRequest(BaseModel):
    approved_ids: List[str]
    write_tags: bool = False
    already_moved: bool = False

class MoveFileRequest(BaseModel):
    move_id: str
    file_path: str
    cleanup: bool = False
