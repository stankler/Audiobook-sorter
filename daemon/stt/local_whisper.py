import subprocess
import tempfile
import os
from pathlib import Path

def extract_audio_chunk(input_path: str, duration_seconds: int = 600) -> str:
    """Use ffmpeg to extract first N seconds as 16kHz mono WAV. Returns temp file path."""
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    subprocess.run([
        "ffmpeg", "-y", "-i", input_path,
        "-t", str(duration_seconds),
        "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        tmp.name
    ], capture_output=True, check=True)
    return tmp.name

def transcribe_local(audio_path: str, model_name: str = "small") -> str:
    """Transcribe audio file using local Whisper. Returns transcript text.

    Requires Python <=3.12 and openai-whisper installed.
    Raises RuntimeError on Python 3.13+ or if whisper not installed.
    """
    try:
        import whisper
    except ImportError as e:
        raise RuntimeError(
            "openai-whisper is not installed. Local STT requires Python <=3.12. "
            "See daemon/requirements-stt.txt"
        ) from e
    model = whisper.load_model(model_name)
    result = model.transcribe(audio_path, language="en", fp16=False)
    return result.get("text", "")
