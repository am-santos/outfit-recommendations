import datetime
import json
from collections.abc import Callable
from typing import Any
from unittest import mock

import requests
from django.test import SimpleTestCase

from weather import client

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# The geocoding API's answer for Lisbon, trimmed to a few of its fields.
LISBON_RESULT = {
    "id": 2267057,
    "name": "Lisbon",
    "latitude": 38.72509,
    "longitude": -9.1498,
    "country_code": "PT",
    "timezone": "Europe/Lisbon",
    "country": "Portugal",
    "admin1": "Lisbon District",
}
GEOCODING_PAYLOAD = {"results": [LISBON_RESULT], "generationtime_ms": 0.08}

# How Open-Meteo rejects a request, with HTTP 400. The reason quotes the
# coordinates, which must not reach the page.
API_ERROR_PAYLOAD = {
    "reason": "Latitude must be in range of -90 to 90°. Given: 91.0.",
    "error": True,
}


def forecast_payload(**today: Any) -> dict[str, Any]:
    """A forecast response for Lisbon; keyword arguments replace today's values."""
    values = {
        "time": "2026-11-10",
        "temperature_2m_max": 19.5,
        "temperature_2m_min": 13.4,
        "apparent_temperature_max": 18.2,
        "apparent_temperature_min": 11.7,
        "precipitation_probability_max": 60,
        "wind_speed_10m_max": 25.3,
    } | today
    return {
        "latitude": 38.746044,
        "longitude": -9.175565,
        "utc_offset_seconds": 0,
        "timezone": "Europe/Lisbon",
        "timezone_abbreviation": "GMT",
        "daily_units": {
            "time": "iso8601",
            "temperature_2m_max": "°C",
            "temperature_2m_min": "°C",
            "apparent_temperature_max": "°C",
            "apparent_temperature_min": "°C",
            "precipitation_probability_max": "%",
            "wind_speed_10m_max": "km/h",
        },
        "daily": {name: [value] for name, value in values.items()},
    }


def fake_response(
    payload: Any = None, *, status: int = 200, body: bytes | None = None
) -> requests.Response:
    """A real Response with a JSON payload, or a raw body, and a status code."""
    response = requests.Response()
    response.status_code = status
    response._content = json.dumps(payload).encode() if body is None else body
    response.encoding = "utf-8"
    return response


def weather_error_message(function: Callable[..., object], *args: Any) -> str:
    """Call the function, which must raise WeatherError; return its message."""
    try:
        function(*args)
    except client.WeatherError as exc:
        return str(exc)
    raise AssertionError("WeatherError not raised")


@mock.patch("weather.client.requests.get")
class GeocodeTests(SimpleTestCase):
    def test_uses_top_match(self, get):
        other_lisbon = {
            "name": "Lisbon",
            "latitude": 44.03146,
            "longitude": -70.10450,
            "country": "United States",
        }
        get.return_value = fake_response({"results": [LISBON_RESULT, other_lisbon]})
        self.assertEqual(
            client.geocode("Lisbon"), (38.72509, -9.1498, "Lisbon", "Portugal")
        )
        get.assert_called_once_with(
            GEOCODING_URL,
            params={"name": "Lisbon", "count": 1, "language": "en", "format": "json"},
            timeout=5,
        )

    def test_missing_or_empty_results_means_not_found(self, get):
        # With no match the API leaves "results" out of the response.
        for payload in [{"generationtime_ms": 0.1}, {"results": []}]:
            with self.subTest(payload=payload):
                get.return_value = fake_response(payload)
                self.assertEqual(
                    weather_error_message(client.geocode, "Nowhereville"),
                    "could not find a city called Nowhereville",
                )

    def test_missing_country_becomes_empty_string(self, get):
        get.return_value = fake_response(
            {"results": [{"name": "Atlantis", "latitude": 1.5, "longitude": -2.5}]}
        )
        self.assertEqual(client.geocode("Atlantis"), (1.5, -2.5, "Atlantis", ""))

    def test_unexpected_result_raises_weather_error(self, get):
        for payload in [
            {"results": [{"name": "Lisbon", "latitude": 38.72509}]},
            {"results": [{"name": "Lisbon", "latitude": None, "longitude": -9.1}]},
            {"results": ["Lisbon"]},
            {"results": "Lisbon"},
        ]:
            with self.subTest(payload=payload):
                get.return_value = fake_response(payload)
                self.assertEqual(
                    weather_error_message(client.geocode, "Lisbon"),
                    "the weather service sent an invalid response",
                )

    def test_request_failure_raises_weather_error(self, get):
        get.side_effect = requests.ConnectTimeout("connect timeout=5")
        self.assertEqual(
            weather_error_message(client.geocode, "Lisbon"),
            "the weather service timed out",
        )


@mock.patch("weather.client.requests.get")
class GetTodayForecastTests(SimpleTestCase):
    def test_fetches_forecast_for_top_match(self, get):
        get.side_effect = [
            fake_response(GEOCODING_PAYLOAD),
            fake_response(forecast_payload()),
        ]
        forecast = client.get_today_forecast("Lisbon")
        # The forecast carries the name the API resolved, with its country.
        self.assertEqual((forecast.city, forecast.country), ("Lisbon", "Portugal"))
        self.assertEqual(
            get.call_args_list,
            [
                mock.call(
                    GEOCODING_URL,
                    params={
                        "name": "Lisbon",
                        "count": 1,
                        "language": "en",
                        "format": "json",
                    },
                    timeout=5,
                ),
                mock.call(
                    FORECAST_URL,
                    params={
                        "latitude": 38.72509,
                        "longitude": -9.1498,
                        "daily": "temperature_2m_max,temperature_2m_min,"
                        "apparent_temperature_max,apparent_temperature_min,"
                        "precipitation_probability_max,wind_speed_10m_max",
                        "timezone": "auto",
                        "forecast_days": 1,
                    },
                    timeout=5,
                ),
            ],
        )

    def test_city_not_found_skips_forecast_request(self, get):
        get.return_value = fake_response({"generationtime_ms": 0.1})
        self.assertEqual(
            weather_error_message(client.get_today_forecast, "Nowhereville"),
            "could not find a city called Nowhereville",
        )
        get.assert_called_once()


class ForecastParsingTests(SimpleTestCase):
    def test_parses_daily_values_into_forecast(self):
        self.assertEqual(
            client.parse_daily(forecast_payload(), "Lisbon", "Portugal"),
            client.Forecast(
                city="Lisbon",
                country="Portugal",
                date=datetime.date(2026, 11, 10),
                temperature_min=13.4,
                temperature_max=19.5,
                feels_like_min=11.7,
                feels_like_max=18.2,
                rain_chance=60,
                wind_max=25.3,
            ),
        )

    def test_uses_local_date_from_response(self):
        # Kiritimati is 14 hours ahead of UTC: from 10:00 on 10 November on a
        # server in UTC, it is already 11 November there. With timezone=auto
        # the response's daily.time is the city's date, and the forecast uses
        # it as it is.
        payload = forecast_payload(time="2026-11-11")
        payload |= {"timezone": "Pacific/Kiritimati", "utc_offset_seconds": 50400}
        forecast = client.parse_daily(payload, "Kiritimati", "Kiribati")
        self.assertEqual(forecast.date, datetime.date(2026, 11, 11))

    def test_null_value_raises_weather_error(self):
        for name in ["time", *client.DAILY_VARIABLES]:
            with self.subTest(name=name):
                payload = forecast_payload(**{name: None})
                self.assertEqual(
                    weather_error_message(
                        client.parse_daily, payload, "Lisbon", "Portugal"
                    ),
                    "incomplete forecast",
                )

    def test_unexpected_payload_raises_weather_error(self):
        missing_wind = forecast_payload()
        del missing_wind["daily"]["wind_speed_10m_max"]
        no_days = forecast_payload()
        no_days["daily"]["time"] = []
        for case, payload in [
            ("no daily", {}),
            ("daily is null", {"daily": None}),
            ("missing variable", missing_wind),
            ("empty arrays", no_days),
            ("date not ISO", forecast_payload(time="10/11/2026")),
            ("not a number", forecast_payload(temperature_2m_max="warm")),
        ]:
            with self.subTest(case):
                self.assertEqual(
                    weather_error_message(
                        client.parse_daily, payload, "Lisbon", "Portugal"
                    ),
                    "the weather service sent an invalid response",
                )


# The city is found, then the forecast request fails. The messages are compared
# in full, so none of them can carry a URL, coordinates or a traceback.
@mock.patch("weather.client.requests.get")
class ForecastErrorTests(SimpleTestCase):
    def forecast_error_message(
        self, get: mock.MagicMock, forecast_response: requests.Response | Exception
    ) -> str:
        get.side_effect = [fake_response(GEOCODING_PAYLOAD), forecast_response]
        return weather_error_message(client.get_today_forecast, "Lisbon")

    def test_timeout_raises_weather_error(self, get):
        timeout = requests.ReadTimeout(
            "HTTPSConnectionPool(host='api.open-meteo.com', port=443): "
            "Read timed out. (read timeout=5)"
        )
        self.assertEqual(
            self.forecast_error_message(get, timeout), "the weather service timed out"
        )

    def test_connection_error_raises_weather_error(self, get):
        error = requests.ConnectionError(
            "HTTPSConnectionPool(host='api.open-meteo.com', port=443): Max retries "
            "exceeded with url: /v1/forecast?latitude=38.72509&longitude=-9.1498"
        )
        self.assertEqual(
            self.forecast_error_message(get, error),
            "the weather service could not be reached",
        )

    def test_http_error_raises_weather_error(self, get):
        response = fake_response(status=503, body=b"<h1>Service Unavailable</h1>")
        self.assertEqual(
            self.forecast_error_message(get, response),
            "the weather service returned an error (HTTP 503)",
        )

    def test_api_error_body_raises_weather_error(self, get):
        # Open-Meteo sends the error body with HTTP 400; it is also caught if
        # it ever comes with HTTP 200.
        for status, message in [
            (400, "the weather service returned an error (HTTP 400)"),
            (200, "the weather service returned an error"),
        ]:
            with self.subTest(status=status):
                response = fake_response(API_ERROR_PAYLOAD, status=status)
                self.assertEqual(self.forecast_error_message(get, response), message)

    def test_malformed_json_raises_weather_error(self, get):
        for body in [
            b"<html>Bad gateway</html>",
            b'{"daily": {"time": ["2026-11-10"]',
            b'["not", "an", "object"]',
        ]:
            with self.subTest(body=body):
                response = fake_response(body=body)
                self.assertEqual(
                    self.forecast_error_message(get, response),
                    "the weather service sent an invalid response",
                )
