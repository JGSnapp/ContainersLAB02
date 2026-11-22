from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import logging
import os
import socket

from fastapi import Depends, FastAPI
from pydantic import BaseModel
from sqlalchemy.orm import Session
import httpx
import redis.asyncio as aioredis

from app import crud
from app.database import engine, get_db
from app.models import Base

logger = logging.getLogger("uvicorn.error")
SECRET_KEY = os.getenv("APP_SECRET", "default_secret")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CACHE_TTL = int(os.getenv("CACHE_TTL", "120"))
HOSTNAME = socket.gethostname()
redis_client: aioredis.Redis | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client
    Base.metadata.create_all(bind=engine)
    try:
        redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
        await redis_client.ping()
        logger.info("Redis connected: %s", REDIS_URL)
    except Exception as exc:
        logger.warning("Redis unavailable (%s) — caching disabled", exc)
        redis_client = None
    yield
    if redis_client:
        await redis_client.aclose()


app = FastAPI(title="Personal Assistant", lifespan=lifespan)


class NoteCreate(BaseModel):
    text: str


def meta() -> dict:
    return {"hostname": HOSTNAME, "server_time": datetime.now(timezone.utc).isoformat()}


@app.get("/")
async def root():
    return {"message": f"👋 Привет!", "service": "personal-assistant", "version": "4.0", "endpoints": ["/me", "/notes", "/weather/{city}", "/secret/{key}", "/cache/stats"], **meta()}


@app.get("/health")
async def health():
    redis_ok = False
    if redis_client:
        try:
            redis_ok = await redis_client.ping()
        except Exception:
            pass
    return {"status": "healthy", "redis": redis_ok, **meta()}


@app.get("/me")
async def me():
    return {"secret_prefix": SECRET_KEY[:6] if SECRET_KEY != "default_secret" else "NOT_SET"}


@app.get("/secret/{key}")
async def secret(key: str):
    if key == SECRET_KEY:
        return {"message": "The secret key is correct!"}
    return {"error": "The secret key is incorrect", "hint": "Check the APP_SECRET environment variable"}


WEATHER_CODES = {0: "☀️ Ясно", 1: "🌤 Малооблачно", 2: "⛅ Переменная облачность", 3: "☁️ Пасмурно", 45: "🌫 Туман", 48: "🌫 Изморозь", 51: "🌦 Лёгкая морось", 53: "🌦 Морось", 55: "🌧 Сильная морось", 61: "🌧 Небольшой дождь", 63: "🌧 Дождь", 65: "🌧 Сильный дождь", 71: "🌨 Снег", 75: "❄️ Сильный снег", 80: "🌦 Ливень", 81: "🌧 Ливень", 82: "⛈ Штормовой ливень", 95: "⛈ Гроза"}


def cache_key(city: str) -> str:
    return f"weather:{city.strip().lower()}"


@app.get("/weather/{city}")
async def weather(city: str):
    key = cache_key(city)
    if redis_client:
        try:
            cached = await redis_client.get(key)
            if cached:
                return {**json.loads(cached), "source": "cache", **meta()}
        except Exception:
            pass
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            geo = (await client.get("https://geocoding-api.open-meteo.com/v1/search", params={"name": city, "count": 1, "language": "ru"})).json()
            if not geo.get("results"):
                return {"error": f"City «{city}» not found", **meta()}
            place = geo["results"][0]
            current = (await client.get("https://api.open-meteo.com/v1/forecast", params={"latitude": place["latitude"], "longitude": place["longitude"], "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code"})).json()["current"]
            result = {"city": place.get("name", city), "country": place.get("country", ""), "coordinates": {"lat": place["latitude"], "lon": place["longitude"]}, "temperature_c": current["temperature_2m"], "humidity_pct": current["relative_humidity_2m"], "wind_km_h": current["wind_speed_10m"], "condition": WEATHER_CODES.get(current.get("weather_code", -1), "Unknown")}
            if redis_client:
                await redis_client.setex(key, CACHE_TTL, json.dumps(result))
            return {**result, "source": "api", **meta()}
    except Exception as exc:
        return {"error": f"Failed to get weather: {type(exc).__name__}: {exc}", **meta()}


@app.get("/cache/stats")
async def cache_stats():
    if not redis_client:
        return {"error": "Redis not available", **meta()}
    keys = []
    async for key in redis_client.scan_iter(match=f"weather:*"):
        keys.append({"key": key, "ttl_seconds": await redis_client.ttl(key)})
    return {"cache_ttl_setting": CACHE_TTL, "cached_cities": len(keys), "keys": keys, **meta()}


@app.post("/notes")
async def create_note(note: NoteCreate, db: Session = Depends(get_db)):
    saved = crud.create_note(db, note.text, os.getenv("APP_OWNER", "unknown"))
    return {"status": "saved", "note_id": saved.id, "text": saved.text[:50]}


@app.get("/notes")
async def list_notes(db: Session = Depends(get_db)):
    notes = crud.get_notes(db)
    return {"count": len(notes), "notes": [{"id": note.id, "text": note.text, "created_at": note.created_at.isoformat()} for note in notes]}
