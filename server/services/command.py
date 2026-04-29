from datetime import datetime, timedelta, timezone
from threading import Lock

import httpx

from . import TempReading

BASE_URL = "https://api.verkada.com"
TOKEN_ENDPOINT = f"{BASE_URL}/token"
DATA_ENDPOINT = f"{BASE_URL}/environment/v1/data"

_token_cache: dict = {}
_token_lock = Lock()


def _get_token(api_key: str, force_refresh: bool = False) -> str:
    with _token_lock:
        cached = _token_cache.get(api_key)
        if not force_refresh and cached:
            return cached
        response = httpx.post(TOKEN_ENDPOINT, headers={"x-api-key": api_key}, timeout=10)
        print(f"VERKADA_TOKEN status={response.status_code} body={response.text!r}", flush=True)
        response.raise_for_status()
        token = response.json()["token"]
        _token_cache[api_key] = token
        return token


def get_last_24h_temps(api_key: str, device_id: str) -> list[TempReading]:
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=24)

    token = _get_token(api_key)
    headers = {"x-verkada-auth": token}
    base_params = {
        "device_id": device_id,
        "start_time": int(start.timestamp()),
        "end_time": int(now.timestamp()),
        "fields": "temperature",
    }

    results = []
    page_token: str | None = None
    for _ in range(50):
        params = {**base_params}
        if page_token:
            params["page_token"] = page_token

        response = httpx.get(DATA_ENDPOINT, headers=headers, params=params, timeout=10)
        if response.status_code == 401:
            token = _get_token(api_key, force_refresh=True)
            headers = {"x-verkada-auth": token}
            response = httpx.get(DATA_ENDPOINT, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        for reading in data.get("data", []):
            if reading.get("temperature") is not None:
                dt = datetime.fromtimestamp(reading["time"], tz=timezone.utc)
                results.append(TempReading(time=dt, temperature_c=reading["temperature"]))

        page_token = data.get("next_page_token") or None
        if not page_token:
            break

    return results
