def transcribe_openai(audio_path: str, api_key: str) -> str:
    """Transcribe using OpenAI Whisper API. Returns transcript text."""
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    with open(audio_path, "rb") as f:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="text",
        )
    return transcript if isinstance(transcript, str) else transcript.text
