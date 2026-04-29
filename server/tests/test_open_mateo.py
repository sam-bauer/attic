import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx
from freezegun import freeze_time

from services import TempReading
from services.open_mateo import BASE_URL, get_last_24h_temps

FROZEN_NOW = "2024-06-15T12:00:00+00:00"


def _make_response(times: list[str], temps: list[float]) -> dict:
    return {"hourly": {"time": times, "temperature_2m": temps}}


@respx.mock
@freeze_time(FROZEN_NOW)
def test_returns_temp_readings():
    now = datetime.fromisoformat(FROZEN_NOW)
    times = [
        (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M"),
        (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
    ]
    respx.get(BASE_URL).mock(
        return_value=httpx.Response(200, json=_make_response(times, [18.5, 19.0]))
    )

    results = get_last_24h_temps(latitude=48.8, longitude=2.3)

    assert len(results) == 2
    assert all(isinstance(r, TempReading) for r in results)
    assert results[0].temperature_c == 18.5
    assert results[1].temperature_c == 19.0


@respx.mock
@freeze_time(FROZEN_NOW)
def test_filters_out_of_window_readings():
    now = datetime.fromisoformat(FROZEN_NOW)
    in_window = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
    out_of_window = (now - timedelta(hours=25)).strftime("%Y-%m-%dT%H:%M")

    respx.get(BASE_URL).mock(
        return_value=httpx.Response(
            200, json=_make_response([out_of_window, in_window], [5.0, 21.0])
        )
    )

    results = get_last_24h_temps(latitude=48.8, longitude=2.3)

    assert len(results) == 1
    assert results[0].temperature_c == 21.0


@respx.mock
@freeze_time(FROZEN_NOW)
def test_empty_response_returns_empty_list():
    respx.get(BASE_URL).mock(
        return_value=httpx.Response(200, json=_make_response([], []))
    )

    assert get_last_24h_temps(latitude=48.8, longitude=2.3) == []


@respx.mock
def test_http_error_raises():
    respx.get(BASE_URL).mock(return_value=httpx.Response(500))

    with pytest.raises(httpx.HTTPStatusError):
        get_last_24h_temps(latitude=48.8, longitude=2.3)


@respx.mock
@freeze_time(FROZEN_NOW)
def test_sends_correct_params():
    now = datetime.fromisoformat(FROZEN_NOW)
    start = now - timedelta(hours=24)
    route = respx.get(BASE_URL).mock(
        return_value=httpx.Response(200, json=_make_response([], []))
    )

    get_last_24h_temps(latitude=51.5, longitude=-0.1)

    sent_params = dict(route.calls.last.request.url.params)
    assert sent_params["latitude"] == "51.5"
    assert sent_params["longitude"] == "-0.1"
    assert sent_params["start_date"] == start.strftime("%Y-%m-%d")
    assert sent_params["end_date"] == now.strftime("%Y-%m-%d")
    assert sent_params["timezone"] == "UTC"


@pytest.mark.integration
def test_integration_returns_readings():
    results = get_last_24h_temps(latitude=48.8566, longitude=2.3522)

    assert isinstance(results, list)
    assert len(results) > 0
    assert all(isinstance(r, TempReading) for r in results)
    assert all(isinstance(r.temperature_c, float) for r in results)
