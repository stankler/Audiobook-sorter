from fastapi import FastAPI
from db import init_db

app = FastAPI(title="Audiobook Organizer")

@app.on_event("startup")
async def startup():
    await init_db()

@app.get("/api/health")
async def health():
    return {"status": "ok"}
