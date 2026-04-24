import base64
import httpx

async def transcribe_google(audio_path: str, api_key: str) -> str:
    """Transcribe using Google Speech-to-Text REST API. Returns transcript text."""
    with open(audio_path, "rb") as f:
        audio_content = base64.b64encode(f.read()).decode()

    payload = {
        "config": {
            "encoding": "LINEAR16",
            "sampleRateHertz": 16000,
            "languageCode": "en-US",
            "model": "default",
        },
        "audio": {"content": audio_content},
    }
    url = f"https://speech.googleapis.com/v1/speech:recognize?key={api_key}"
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(url, json=payload)
        r.raise_for_status()
        data = r.json()

    results = data.get("results", [])
    return " ".join(
        alt["transcript"]
        for r in results
        for alt in r.get("alternatives", [])[:1]
    )
