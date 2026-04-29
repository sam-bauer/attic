from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx
from freezegun import freeze_time

from services import TempReading
from services.command import DATA_ENDPOINT, TOKEN_ENDPOINT, get_last_24h_temps

FROZEN_NOW = "2024-06-15T12:00:00+00:00"
API_KEY = "test-api-key"
DEVICE_ID = "test-device-id"
TOKEN = "test-token"


def _mock_token(token: str = TOKEN) -> None:
    respx.post(TOKEN_ENDPOINT).mock(
        return_value=httpx.Response(200, json={"token": token})
    )


def _make_response(readings: list[dict]) -> dict:
    return {"data": readings, "device_id": DEVICE_ID}


def _reading(epoch: int, temp: float) -> dict:
    return {"time": epoch, "temperature": temp}


@respx.mock
@freeze_time(FROZEN_NOW)
def test_returns_temp_readings():
    now = datetime.fromisoformat(FROZEN_NOW)
    _mock_token()
    respx.get(DATA_ENDPOINT).mock(
        return_value=httpx.Response(
            200,
            json=_make_response([
                _reading(int((now - timedelta(hours=2)).timestamp()), 20.1),
                _reading(int((now - timedelta(hours=1)).timestamp()), 21.5),
            ]),
        )
    )

    results = get_last_24h_temps(API_KEY, DEVICE_ID)

    assert len(results) == 2
    assert all(isinstance(r, TempReading) for r in results)
    assert results[0].temperature_c == 20.1
    assert results[1].temperature_c == 21.5


@respx.mock
@freeze_time(FROZEN_NOW)
def test_empty_data_list_returns_empty():
    _mock_token()
    respx.get(DATA_ENDPOINT).mock(
        return_value=httpx.Response(200, json=_make_response([]))
    )

    assert get_last_24h_temps(API_KEY, DEVICE_ID) == []


@respx.mock
@freeze_time(FROZEN_NOW)
def test_missing_data_key_returns_empty():
    _mock_token()
    respx.get(DATA_ENDPOINT).mock(
        return_value=httpx.Response(200, json={"device_id": DEVICE_ID})
    )

    assert get_last_24h_temps(API_KEY, DEVICE_ID) == []


@respx.mock
@freeze_time(FROZEN_NOW)
def test_reading_without_temperature_field_is_skipped():
    now = datetime.fromisoformat(FROZEN_NOW)
    _mock_token()
    respx.get(DATA_ENDPOINT).mock(
        return_value=httpx.Response(
            200,
            json=_make_response([
                {"time": int((now - timedelta(hours=2)).timestamp())},
                _reading(int((now - timedelta(hours=1)).timestamp()), 21.5),
            ]),
        )
    )

    results = get_last_24h_temps(API_KEY, DEVICE_ID)

    assert len(results) == 1
    assert results[0].temperature_c == 21.5


@respx.mock
def test_token_error_raises():
    respx.post(TOKEN_ENDPOINT).mock(return_value=httpx.Response(401))

    with pytest.raises(httpx.HTTPStatusError):
        get_last_24h_temps(API_KEY, DEVICE_ID)


@respx.mock
def test_data_http_error_raises():
    _mock_token()
    respx.get(DATA_ENDPOINT).mock(return_value=httpx.Response(400))

    with pytest.raises(httpx.HTTPStatusError):
        get_last_24h_temps(API_KEY, DEVICE_ID)


@respx.mock
@freeze_time(FROZEN_NOW)
def test_sends_correct_params_and_headers():
    now = datetime.fromisoformat(FROZEN_NOW)
    start = now - timedelta(hours=24)
    _mock_token()
    data_route = respx.get(DATA_ENDPOINT).mock(
        return_value=httpx.Response(200, json=_make_response([]))
    )

    get_last_24h_temps(API_KEY, DEVICE_ID)

    request = data_route.calls.last.request
    params = dict(request.url.params)
    assert params["device_id"] == DEVICE_ID
    assert params["start_time"] == str(int(start.timestamp()))
    assert params["end_time"] == str(int(now.timestamp()))
    assert params["fields"] == "temperature"
    assert request.headers["x-verkada-auth"] == TOKEN


@respx.mock
@freeze_time(FROZEN_NOW)
def test_api_key_sent_to_token_endpoint():
    token_route = respx.post(TOKEN_ENDPOINT).mock(
        return_value=httpx.Response(200, json={"token": TOKEN})
    )
    respx.get(DATA_ENDPOINT).mock(
        return_value=httpx.Response(200, json=_make_response([]))
    )

    get_last_24h_temps(API_KEY, DEVICE_ID)

    assert token_route.calls.last.request.headers["x-api-key"] == API_KEY


@respx.mock
@freeze_time(FROZEN_NOW)
def test_timestamps_are_utc():
    now = datetime.fromisoformat(FROZEN_NOW)
    epoch = int((now - timedelta(hours=3)).timestamp())
    _mock_token()
    respx.get(DATA_ENDPOINT).mock(
        return_value=httpx.Response(200, json=_make_response([_reading(epoch, 18.0)]))
    )

    results = get_last_24h_temps(API_KEY, DEVICE_ID)

    assert results[0].time.tzinfo == timezone.utc
    assert results[0].time == datetime.fromtimestamp(epoch, tz=timezone.utc)


@pytest.mark.integration
def test_integration_returns_readings():
    import os

    results = get_last_24h_temps(
        api_key=os.environ["COMMAND_API_KEY"],
        device_id=os.environ["COMMAND_DEVICE_ID"],
    )

    assert isinstance(results, list)
    assert len(results) > 0
    assert all(isinstance(r, TempReading) for r in results)
    assert all(isinstance(r.temperature_c, float) for r in results)
