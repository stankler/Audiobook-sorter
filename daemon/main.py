from fastapi import FastAPI
from db import init_db
from config import load_config, save_config
from models import Config

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
