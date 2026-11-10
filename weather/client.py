"""Today's forecast for one city, from Open-Meteo.

The city name is turned into coordinates with the geocoding API, then the
daily forecast for those coordinates is fetched. Every failure becomes a
WeatherError whose message is short and safe to show on a page.
"""

import datetime
from dataclasses import dataclass
from typing import Any

import requests

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Seconds to wait for each request.
TIMEOUT = 5

# Today's values requested from the forecast API, in Open-Meteo's default
# units: °C, % and km/h.
DAILY_VARIABLES = [
    "temperature_2m_max",
    "temperature_2m_min",
    "apparent_temperature_max",
    "apparent_temperature_min",
    "precipitation_probability_max",
    "wind_speed_10m_max",
]

INVALID_RESPONSE = "the weather service sent an invalid response"


class WeatherError(Exception):
    """Today's forecast could not be fetched.

    The message is short and safe to show: it never includes a request URL,
    coordinates or a traceback.
    """


@dataclass(frozen=True)
class Forecast:
    city: str
    country: str
    date: datetime.date
    temperature_min: float
    temperature_max: float
    feels_like_min: float
    feels_like_max: float
    rain_chance: int  # precipitation_probability_max, %
    wind_max: float  # wind_speed_10m_max, km/h


def get_today_forecast(city: str) -> Forecast:
    """Return today's forecast for the top match for the city name."""
    latitude, longitude, name, country = geocode(city)
    return parse_daily(fetch_forecast(latitude, longitude), name, country)


def geocode(city: str) -> tuple[float, float, str, str]:
    """Return the latitude, longitude, name and country of the top match."""
    payload = _get_json(
        GEOCODING_URL,
        {"name": city, "count": 1, "language": "en", "format": "json"},
    )
    results = payload.get("results")
    if not results:
        raise WeatherError(f"could not find a city called {city}")
    try:
        top = results[0]
        # Some places have no country, and the API then leaves the key out.
        return (
            float(top["latitude"]),
            float(top["longitude"]),
            top["name"],
            top.get("country", ""),
        )
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise WeatherError(INVALID_RESPONSE) from exc


def fetch_forecast(latitude: float, longitude: float) -> dict[str, Any]:
    """Return the forecast API's response for today at the coordinates."""
    return _get_json(
        FORECAST_URL,
        {
            "latitude": latitude,
            "longitude": longitude,
            "daily": ",".join(DAILY_VARIABLES),
            # Days follow the place's own time zone, so daily.time[0] is the
            # city's today rather than the server's.
            "timezone": "auto",
            "forecast_days": 1,
        },
    )


def parse_daily(payload: dict[str, Any], city: str, country: str) -> Forecast:
    """Build a Forecast from a forecast API response."""
    try:
        daily = payload["daily"]
        today = {name: daily[name][0] for name in ["time", *DAILY_VARIABLES]}
    except (KeyError, IndexError, TypeError) as exc:
        raise WeatherError(INVALID_RESPONSE) from exc
    if any(value is None for value in today.values()):
        raise WeatherError("incomplete forecast")
    try:
        return Forecast(
            city=city,
            country=country,
            date=datetime.date.fromisoformat(today["time"]),
            temperature_min=float(today["temperature_2m_min"]),
            temperature_max=float(today["temperature_2m_max"]),
            feels_like_min=float(today["apparent_temperature_min"]),
            feels_like_max=float(today["apparent_temperature_max"]),
            rain_chance=int(today["precipitation_probability_max"]),
            wind_max=float(today["wind_speed_10m_max"]),
        )
    except (TypeError, ValueError) as exc:
        raise WeatherError(INVALID_RESPONSE) from exc


def _get_json(url: str, params: dict[str, str | int | float]) -> dict[str, Any]:
    """Send a GET request and return the JSON object in the response."""
    try:
        response = requests.get(url, params=params, timeout=TIMEOUT)
    except requests.Timeout as exc:
        raise WeatherError("the weather service timed out") from exc
    except requests.RequestException as exc:
        raise WeatherError("the weather service could not be reached") from exc
    if not response.ok:
        raise WeatherError(
            f"the weather service returned an error (HTTP {response.status_code})"
        )
    try:
        payload = response.json()
    except ValueError as exc:  # requests' JSONDecodeError is a ValueError
        raise WeatherError(INVALID_RESPONSE) from exc
    if not isinstance(payload, dict):
        raise WeatherError(INVALID_RESPONSE)
    # Open-Meteo describes a rejected request as {"error": true, "reason": ...}.
    # The reason can quote the coordinates, so it is not passed on.
    if payload.get("error"):
        raise WeatherError("the weather service returned an error")
    return payload
