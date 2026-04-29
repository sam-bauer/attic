from datetime import datetime, timedelta, timezone

import httpx

from . import TempReading

BASE_URL = "https://api.open-meteo.com/v1/forecast"


def get_last_24h_temps(latitude: float, longitude: float) -> list[TempReading]:
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=24)

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "temperature_2m",
        "past_days": 1,
        "forecast_days": 1,
        "timezone": "UTC",
    }

    response = httpx.get(BASE_URL, params=params)
    response.raise_for_status()
    data = response.json()

    times = data["hourly"]["time"]
    temps = data["hourly"]["temperature_2m"]

    results = []
    for t, temp in zip(times, temps):
        if temp is None:
            continue
        dt = datetime.fromisoformat(t).replace(tzinfo=timezone.utc)
        if start <= dt <= now:
            results.append(TempReading(time=dt, temperature_c=temp))

    return results
