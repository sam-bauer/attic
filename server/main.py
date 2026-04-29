import logging
import os
import time
from datetime import datetime, timezone
from threading import Lock

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from services.command import get_last_24h_temps as get_sensor_temps
from services.open_mateo import get_last_24h_temps as get_weather_temps

load_dotenv()

CACHE_TTL = int(os.getenv("CACHE_TTL_SECONDS", "300"))
_cors_env = os.getenv("CORS_ORIGINS", "*")
CORS_ORIGINS = [o.strip() for o in _cors_env.split(",")] if _cors_env != "*" else ["*"]

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET"],
    allow_headers=["*"],
)


class DataPoint(BaseModel):
    x: datetime
    y: float


class Dataset(BaseModel):
    label: str
    data: list[DataPoint]


class ChartResponse(BaseModel):
    datasets: list[Dataset]
    cached_at: datetime


_cache: dict = {}
_lock = Lock()


def _fetch_fresh() -> ChartResponse:
    api_key = os.getenv("COMMAND_API_KEY", "")
    device_id = os.getenv("COMMAND_DEVICE_ID", "")
    latitude = float(os.getenv("LATITUDE", "0"))
    longitude = float(os.getenv("LONGITUDE", "0"))

    sensor_readings = get_sensor_temps(api_key, device_id) if api_key and device_id else []
    weather_readings = get_weather_temps(latitude, longitude)

    return ChartResponse(
        datasets=[
            Dataset(
                label="Sensor Temperature",
                data=[DataPoint(x=r.time, y=r.temperature_c) for r in sensor_readings],
            ),
            Dataset(
                label="Outdoor Temperature",
                data=[DataPoint(x=r.time, y=r.temperature_c) for r in weather_readings],
            ),
        ],
        cached_at=datetime.now(timezone.utc),
    )


def _get_cached() -> ChartResponse:
    with _lock:
        entry = _cache.get("data")
        if entry is not None and time.monotonic() - entry["fetched_at"] < CACHE_TTL:
            return entry["value"]

        result = _fetch_fresh()
        _cache["data"] = {"value": result, "fetched_at": time.monotonic()}
        return result


def _cors_header(request: Request) -> dict:
    origin = request.headers.get("origin", "")
    if not origin:
        return {}
    if CORS_ORIGINS == ["*"] or origin in CORS_ORIGINS:
        return {"access-control-allow-origin": "*" if CORS_ORIGINS == ["*"] else origin}
    return {}


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code >= 500:
        logging.exception(exc.detail)
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=_cors_header(request))


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logging.exception("Unhandled error on %s", request.url.path)
    return JSONResponse({"detail": str(exc)}, status_code=500, headers=_cors_header(request))


@app.get("/data", response_model=ChartResponse)
def read_data():
    return _get_cached()


@app.get("/health")
def health():
    return {"status": "ok"}
