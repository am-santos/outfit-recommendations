import dataclasses
import datetime
from unittest import mock

import requests
from django.test import TestCase, override_settings
from django.urls import reverse

from wardrobe import models
from weather import client

LISBON_FORECAST = client.Forecast(
    city="Lisbon",
    country="Portugal",
    date=datetime.date(2026, 11, 10),
    temperature_min=13.4,
    temperature_max=19.5,
    feels_like_min=11.7,
    feels_like_max=18.2,
    rain_chance=60,
    wind_max=25.3,
)

ATTRIBUTION = '<a href="https://open-meteo.com/">Weather data by Open-Meteo.com</a>'


def create_item(name: str) -> models.ClothingItem:
    return models.ClothingItem.objects.create(
        name=name, category="top", colour="White", material="cotton", warmth=1
    )


@mock.patch("weather.client.get_today_forecast", return_value=LISBON_FORECAST)
class TodayPageTests(TestCase):
    def test_url_is_site_root(self, get_today_forecast):
        self.assertEqual(reverse("suggestions:today"), "/")

    def test_shows_forecast_with_city_date_and_attribution(self, get_today_forecast):
        response = self.client.get(reverse("suggestions:today"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "suggestions/today.html")
        self.assertContains(response, "<h2>Lisbon, Portugal</h2>", html=True)
        self.assertContains(
            response,
            '<time datetime="2026-11-10">Tuesday 10 November 2026</time>',
            html=True,
        )
        self.assertContains(response, ATTRIBUTION, html=True)
        self.assertNotContains(response, "unavailable")

    def test_shows_forecast_values(self, get_today_forecast):
        get_today_forecast.return_value = dataclasses.replace(
            LISBON_FORECAST, temperature_max=19.0
        )
        response = self.client.get(reverse("suggestions:today"))
        # One decimal place at most, and none for a whole number.
        self.assertContains(
            response,
            "<ul><li>Temperature: 13.4–19 °C</li><li>Feels like: 11.7–18.2 °C</li>"
            "<li>Chance of rain: 60%</li><li>Wind: up to 25.3 km/h</li></ul>",
            html=True,
        )

    @override_settings(CITY="Porto")
    def test_fetches_forecast_for_configured_city(self, get_today_forecast):
        self.client.get(reverse("suggestions:today"))
        get_today_forecast.assert_called_once_with("Porto")

    def test_shows_city_alone_when_country_missing(self, get_today_forecast):
        get_today_forecast.return_value = dataclasses.replace(
            LISBON_FORECAST, city="Atlantis", country=""
        )
        response = self.client.get(reverse("suggestions:today"))
        self.assertContains(response, "<h2>Atlantis</h2>", html=True)
        self.assertNotContains(response, "Atlantis,")

    def test_shows_unavailable_message_when_weather_fails(self, get_today_forecast):
        get_today_forecast.side_effect = client.WeatherError(
            "the weather service timed out"
        )
        create_item("White T-shirt")
        with self.assertLogs("suggestions.views", "WARNING"):
            response = self.client.get(reverse("suggestions:today"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "<p>Today's forecast is unavailable: the weather service timed out.</p>",
            html=True,
        )
        self.assertNotContains(response, "<h2>")
        self.assertNotContains(response, "Open-Meteo.com")
        # The rest of the page still works.
        self.assertContains(response, "<p>Your wardrobe has 1 item.</p>", html=True)

    def test_logs_weather_error_without_traceback(self, get_today_forecast):
        error = client.WeatherError("the weather service timed out")
        error.__cause__ = requests.ReadTimeout(
            "HTTPSConnectionPool(host='api.open-meteo.com', port=443): Read timed out."
        )
        get_today_forecast.side_effect = error
        with self.assertLogs("suggestions.views", "WARNING") as logs:
            self.client.get(reverse("suggestions:today"))
        # The message and the class of the original exception, nothing else.
        self.assertEqual(
            logs.output,
            [
                (
                    "WARNING:suggestions.views:Forecast unavailable: "
                    "the weather service timed out (ReadTimeout)"
                )
            ],
        )
        self.assertIsNone(logs.records[0].exc_info)

    def test_shows_wardrobe_item_count(self, get_today_forecast):
        url = reverse("suggestions:today")
        self.assertContains(
            self.client.get(url), "<p>Your wardrobe has 0 items.</p>", html=True
        )
        create_item("White T-shirt")
        self.assertContains(
            self.client.get(url), "<p>Your wardrobe has 1 item.</p>", html=True
        )
        create_item("Grey T-shirt")
        self.assertContains(
            self.client.get(url), "<p>Your wardrobe has 2 items.</p>", html=True
        )

    def test_suggest_button_is_disabled_placeholder(self, get_today_forecast):
        create_item("White T-shirt")
        response = self.client.get(reverse("suggestions:today"))
        self.assertContains(
            response,
            '<button type="button" disabled>Suggest an outfit</button>',
            html=True,
        )
        self.assertNotContains(response, "<form")

    def test_page_uses_base_layout_with_today_first_in_nav(self, get_today_forecast):
        response = self.client.get(reverse("suggestions:today"))
        self.assertTemplateUsed(response, "base.html")
        self.assertContains(
            response, "<title>Today – What should I wear today?</title>", html=True
        )
        self.assertContains(
            response,
            '<nav><a href="/">Today</a><a href="/wardrobe/">Wardrobe</a></nav>',
            html=True,
        )
