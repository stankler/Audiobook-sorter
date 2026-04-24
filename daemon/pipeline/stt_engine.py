import tempfile
import os
from models import STTEngine

STT_CHUNK_SECONDS = 600  # 10 minutes

async def transcribe_book(
    first_file: str,
    engine: STTEngine,
    whisper_model: str = "small",
    api_key: str = "",
) -> str | None:
    """Extract first 10 min of audio and transcribe. Returns text or None on failure."""
    if engine == STTEngine.NONE:
        return None

    tmp_wav = None
    try:
        from stt.local_whisper import extract_audio_chunk
        tmp_wav = extract_audio_chunk(first_file, STT_CHUNK_SECONDS)

        if engine == STTEngine.LOCAL_WHISPER:
            from stt.local_whisper import transcribe_local
            return transcribe_local(tmp_wav, whisper_model)
        elif engine == STTEngine.OPENAI_API:
            from stt.openai_stt import transcribe_openai
            return transcribe_openai(tmp_wav, api_key)
        elif engine == STTEngine.GOOGLE_SPEECH:
            from stt.google_stt import transcribe_google
            return await transcribe_google(tmp_wav, api_key)
    except Exception:
        return None
    finally:
        if tmp_wav and os.path.exists(tmp_wav):
            os.unlink(tmp_wav)

def extract_title_from_transcript(transcript: str) -> tuple[str | None, str | None]:
    """Look for 'This is [Title] by [Author]' or repeated title patterns."""
    import re
    m = re.search(
        r"(?:this is|i[''`]?m reading|welcome to)\s+(.+?)\s+by\s+([A-Z][a-zA-Z\s,\.]+)",
        transcript, re.IGNORECASE
    )
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return None, None
