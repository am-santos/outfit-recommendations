import copy
import dataclasses
import datetime
import json
import os
from typing import Any
from unittest import mock

import anthropic
import httpx2
import requests
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from suggestions import llm, service
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

# Shown instead of the Suggest form when the wardrobe is empty.
ADD_CLOTHES = (
    '<p><a href="/wardrobe/add/">Add some clothes</a> to your wardrobe first.</p>'
)


def create_item(name: str) -> models.ClothingItem:
    return models.ClothingItem.objects.create(
        name=name, category="top", colour="White", material="cotton", warmth=1
    )


def suggest_form(csrf_token: str, button: str) -> str:
    """The Suggest form, posting to the today page, with the page's CSRF token."""
    return (
        '<form method="post" action="/">'
        '<input type="hidden" name="csrfmiddlewaretoken" '
        f'value="{csrf_token}">'
        f"{button}</form>"
    )


# A wardrobe in the list page's order (category, then name), with fixed ids.
# The items are not saved: the prompt and the checks need no database.
SCARF = models.ClothingItem(
    id=14,
    name="Grey scarf",
    category="accessory",
    colour="Grey",
    size="One size",
    material="wool",
    warmth=4,
)
JEANS = models.ClothingItem(
    id=9,
    name="Blue jeans",
    category="bottom",
    colour="Blue",
    size="W32 L34",
    material="denim",
    warmth=3,
)
COAT = models.ClothingItem(
    id=7,
    name="Navy wool coat",
    category="outer",
    colour="Navy",
    size="XL",
    material="wool",
    warmth=5,
)
BOOTS = models.ClothingItem(
    id=12,
    name="Leather boots",
    category="shoes",
    colour="Brown",
    size="UK 9",
    material="leather",
    warmth=3,
    waterproof=True,
)
SHIRT = models.ClothingItem(
    id=3,
    name="White T-shirt",
    category="top",
    colour="White",
    size="Medium",
    material="cotton",
    warmth=1,
    layerable=True,
)
WARDROBE = [SCARF, JEANS, COAT, BOOTS, SHIRT]
ITEMS_BY_ID = {item.pk: item for item in WARDROBE}


def save_wardrobe() -> None:
    """Save the wardrobe above, with its ids, for the view tests.

    Copies are saved, so the items above stay as they are.
    """
    models.ClothingItem.objects.bulk_create([copy.copy(item) for item in WARDROBE])


REASON = "Jeans and a T-shirt under the wool coat, with boots in case of rain."
VALID_ANSWER = {"item_ids": [9, 3, 7, 12], "reason": REASON}

# The schema sent with every request: item ids and a reason, nothing else.
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "item_ids": {"type": "array", "items": {"type": "integer"}},
        "reason": {"type": "string"},
    },
    "required": ["item_ids", "reason"],
    "additionalProperties": False,
}

# complete_json passes on whatever schema it is given.
ANSWER_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}

INVALID_RESPONSE = "the Anthropic API sent an invalid response"

MESSAGES_REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def fake_message(
    text: str | None, stop_reason: anthropic.types.StopReason = "end_turn"
) -> anthropic.types.Message:
    """A Messages API response: a thinking block, then the text block if any."""
    content: list[anthropic.types.ContentBlock] = [
        # Thinking text is left out by default: the block holds a signature.
        anthropic.types.ThinkingBlock(type="thinking", thinking="", signature="c2ln")
    ]
    if text is not None:
        content.append(anthropic.types.TextBlock(type="text", text=text))
    return anthropic.types.Message(
        id="msg_01",
        type="message",
        role="assistant",
        model="claude-haiku-5-5",
        content=content,
        stop_reason=stop_reason,
        stop_sequence=None,
        usage=anthropic.types.Usage(input_tokens=1500, output_tokens=400),
    )


def status_error(
    error_class: type[anthropic.APIStatusError],
    status: int,
    error_type: str,
    message: str,
) -> anthropic.APIStatusError:
    """An HTTP error from the API, built the way the SDK builds it."""
    body = {
        "type": "error",
        "error": {"type": error_type, "message": message},
        "request_id": "req_01",
    }
    response = httpx2.Response(status, request=MESSAGES_REQUEST, json=body)
    return error_class(f"Error code: {status} - {body}", response=response, body=body)


def rejection_message(data: dict[str, Any]) -> str:
    """Check the answer, which must be rejected; return the problem it names."""
    try:
        service.parse_suggestion(data, ITEMS_BY_ID)
    except service.InvalidSuggestion as exc:
        return str(exc)
    raise AssertionError("InvalidSuggestion not raised")


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

    def test_date_comes_from_forecast_not_server_clock(self, get_today_forecast):
        # At most one of two dates can be the server's today, so a page showing
        # the server's date fails for one of them, whatever day the tests run.
        for date, shown in [
            (datetime.date(2026, 11, 10), "Tuesday 10 November 2026"),
            (datetime.date(2026, 11, 11), "Wednesday 11 November 2026"),
        ]:
            with self.subTest(date=date):
                get_today_forecast.return_value = dataclasses.replace(
                    LISBON_FORECAST, date=date
                )
                response = self.client.get(reverse("suggestions:today"))
                self.assertContains(
                    response,
                    f'<time datetime="{date.isoformat()}">{shown}</time>',
                    html=True,
                )

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

    def test_suggest_form_posts_to_today_page(self, get_today_forecast):
        create_item("White T-shirt")
        response = self.client.get(reverse("suggestions:today"))
        self.assertContains(
            response,
            suggest_form(
                str(response.context["csrf_token"]),
                '<button type="submit">Suggest an outfit</button>',
            ),
            html=True,
        )
        self.assertNotContains(response, "Add some clothes")

    def test_suggest_button_replaced_when_wardrobe_empty(self, get_today_forecast):
        response = self.client.get(reverse("suggestions:today"))
        self.assertContains(response, ADD_CLOTHES, html=True)
        self.assertNotContains(response, "<form")
        self.assertNotContains(response, "Suggest an outfit")

    def test_suggest_button_disabled_when_forecast_unavailable(
        self, get_today_forecast
    ):
        get_today_forecast.side_effect = client.WeatherError(
            "the weather service timed out"
        )
        create_item("White T-shirt")
        with self.assertLogs("suggestions.views", "WARNING"):
            response = self.client.get(reverse("suggestions:today"))
        self.assertContains(
            response,
            suggest_form(
                str(response.context["csrf_token"]),
                '<button type="submit" disabled>Suggest an outfit</button>',
            ),
            html=True,
        )

    @mock.patch("suggestions.service.suggest_outfit")
    def test_get_shows_no_suggestion(self, suggest_outfit, get_today_forecast):
        create_item("White T-shirt")
        response = self.client.get(reverse("suggestions:today"))
        suggest_outfit.assert_not_called()
        self.assertNotIn("suggestion", response.context)
        self.assertNotContains(response, "Suggested outfit")
        self.assertNotContains(response, "<table")

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


@mock.patch("weather.client.get_today_forecast", return_value=LISBON_FORECAST)
@mock.patch("suggestions.service.suggest_outfit")
class SuggestViewTests(TestCase):
    def test_post_to_today_url_shows_items_and_reason(
        self, suggest_outfit, get_today_forecast
    ):
        save_wardrobe()
        suggest_outfit.return_value = service.Suggestion(
            items=(JEANS, SHIRT, COAT, BOOTS), reason=REASON
        )
        response = self.client.post(reverse("suggestions:today"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "suggestions/today.html")
        # The forecast is fetched again, and sent with the whole wardrobe.
        get_today_forecast.assert_called_once()
        suggest_outfit.assert_called_once_with(LISBON_FORECAST, WARDROBE)
        self.assertContains(response, "<h2>Lisbon, Portugal</h2>", html=True)
        # The items in the order given, with the wardrobe list's labels, then
        # the reason.
        self.assertContains(
            response,
            "<h2>Suggested outfit</h2>"
            "<table><thead><tr>"
            '<th scope="col">Name</th><th scope="col">Category</th>'
            '<th scope="col">Colour</th><th scope="col">Size</th>'
            '<th scope="col">Material</th><th scope="col">Warmth</th>'
            '<th scope="col">Waterproof</th><th scope="col">Layerable</th>'
            "</tr></thead><tbody>"
            '<tr><th scope="row">Blue jeans</th><td>Bottom</td><td>Blue</td>'
            "<td>W32 L34</td><td>Denim</td><td>3</td><td>No</td><td>No</td></tr>"
            '<tr><th scope="row">White T-shirt</th><td>Top</td><td>White</td>'
            "<td>Medium</td><td>Cotton</td><td>1 – very light</td><td>No</td>"
            "<td>Yes</td></tr>"
            '<tr><th scope="row">Navy wool coat</th><td>Outer layer</td>'
            "<td>Navy</td><td>XL</td><td>Wool</td><td>5 – very warm</td>"
            "<td>No</td><td>No</td></tr>"
            '<tr><th scope="row">Leather boots</th><td>Shoes</td><td>Brown</td>'
            "<td>UK 9</td><td>Leather</td><td>3</td><td>Yes</td><td>No</td></tr>"
            "</tbody></table>"
            f"<p>{REASON}</p>",
            html=True,
        )
        # The form stays, to ask for another suggestion.
        self.assertContains(
            response,
            suggest_form(
                str(response.context["csrf_token"]),
                '<button type="submit">Suggest an outfit</button>',
            ),
            html=True,
        )

    def test_reason_is_escaped(self, suggest_outfit, get_today_forecast):
        save_wardrobe()
        suggest_outfit.return_value = service.Suggestion(
            items=(JEANS,), reason='Jeans <script>alert("rain")</script> & boots'
        )
        response = self.client.post(reverse("suggestions:today"))
        # The reason is the LLM's text: it is shown as text, never as markup.
        self.assertContains(
            response,
            "<p>Jeans &lt;script&gt;alert(&quot;rain&quot;)&lt;/script&gt; "
            "&amp; boots</p>",
        )
        self.assertNotContains(response, "<script")

    def test_reason_keeps_its_line_breaks(self, suggest_outfit, get_today_forecast):
        save_wardrobe()
        suggest_outfit.return_value = service.Suggestion(
            items=(JEANS,), reason="Jeans for the cold.\nBoots for the rain."
        )
        response = self.client.post(reverse("suggestions:today"))
        # A line break in the LLM's text stays a line break on the page.
        self.assertContains(
            response, "<p>Jeans for the cold.<br>Boots for the rain.</p>"
        )

    def test_shows_message_when_suggestion_rejected(
        self, suggest_outfit, get_today_forecast
    ):
        save_wardrobe()
        suggest_outfit.side_effect = service.InvalidSuggestion("chose no items")
        with self.assertLogs("suggestions.views", "WARNING"):
            response = self.client.post(reverse("suggestions:today"))
        self.assertEqual(response.status_code, 200)
        # The message, then the Suggest form to try again.
        self.assertContains(
            response,
            "<p>Could not get a valid suggestion. Try again.</p>"
            + suggest_form(
                str(response.context["csrf_token"]),
                '<button type="submit">Suggest an outfit</button>',
            ),
            html=True,
        )
        self.assertNotContains(response, "Suggested outfit")
        # What was wrong goes to the log, not to the page.
        self.assertNotContains(response, "chose no items")

    def test_shows_message_when_llm_unavailable(
        self, suggest_outfit, get_today_forecast
    ):
        save_wardrobe()
        suggest_outfit.side_effect = llm.LLMError("ANTHROPIC_API_KEY is not set")
        with self.assertLogs("suggestions.views", "WARNING"):
            response = self.client.post(reverse("suggestions:today"))
        self.assertEqual(response.status_code, 200)
        # The Suggest button reads Try again, and posts to the page again.
        self.assertContains(
            response,
            "<p>The suggestion service is unavailable right now.</p>"
            + suggest_form(
                str(response.context["csrf_token"]),
                '<button type="submit">Try again</button>',
            ),
            html=True,
        )
        self.assertNotContains(response, "Suggest an outfit")
        self.assertNotContains(response, "Suggested outfit")
        # What went wrong goes to the log, not to the page.
        self.assertNotContains(response, "ANTHROPIC_API_KEY")

    def test_empty_wardrobe_does_not_call_llm(self, suggest_outfit, get_today_forecast):
        url = reverse("suggestions:today")
        response = self.client.post(url)
        suggest_outfit.assert_not_called()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<h2>Lisbon, Portugal</h2>", html=True)
        self.assertContains(response, ADD_CLOTHES, html=True)
        # Exactly the page a GET shows.
        self.assertEqual(response.content, self.client.get(url).content)

    def test_forecast_unavailable_does_not_call_llm(
        self, suggest_outfit, get_today_forecast
    ):
        save_wardrobe()
        get_today_forecast.side_effect = client.WeatherError(
            "the weather service timed out"
        )
        with self.assertLogs("suggestions.views", "WARNING"):
            response = self.client.post(reverse("suggestions:today"))
        suggest_outfit.assert_not_called()
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "<p>Today's forecast is unavailable: the weather service timed out.</p>",
            html=True,
        )
        self.assertContains(
            response,
            suggest_form(
                str(response.context["csrf_token"]),
                '<button type="submit" disabled>Suggest an outfit</button>',
            ),
            html=True,
        )

    def test_post_without_csrf_token_does_not_call_llm(
        self, suggest_outfit, get_today_forecast
    ):
        # Otherwise a page on another site could make the owner's browser ask
        # for suggestions, each one a paid LLM call.
        save_wardrobe()
        response = Client(enforce_csrf_checks=True).post(reverse("suggestions:today"))
        self.assertEqual(response.status_code, 403)
        suggest_outfit.assert_not_called()

    def test_logs_llm_error_without_traceback(self, suggest_outfit, get_today_forecast):
        save_wardrobe()
        http_error = llm.LLMError("the Anthropic API returned an error (HTTP 401)")
        http_error.__cause__ = status_error(
            anthropic.AuthenticationError,
            401,
            "authentication_error",
            "invalid x-api-key",
        )
        for error, logged in [
            (
                llm.LLMError("ANTHROPIC_API_KEY is not set"),
                "ANTHROPIC_API_KEY is not set (LLMError)",
            ),
            (
                http_error,
                "the Anthropic API returned an error (HTTP 401) (AuthenticationError)",
            ),
        ]:
            with self.subTest(logged=logged):
                suggest_outfit.side_effect = error
                with self.assertLogs("suggestions.views", "WARNING") as logs:
                    self.client.post(reverse("suggestions:today"))
                # The message and the class of the original exception, nothing
                # else.
                self.assertEqual(
                    logs.output,
                    [
                        (
                            "WARNING:suggestions.views:"
                            f"Suggestion service unavailable: {logged}"
                        )
                    ],
                )
                self.assertIsNone(logs.records[0].exc_info)

    def test_logs_why_suggestion_was_rejected(self, suggest_outfit, get_today_forecast):
        save_wardrobe()
        suggest_outfit.side_effect = service.InvalidSuggestion(
            "used ids that are not in the wardrobe: 42, 99"
        )
        with self.assertLogs("suggestions.views", "WARNING") as logs:
            self.client.post(reverse("suggestions:today"))
        self.assertEqual(
            logs.output,
            [
                (
                    "WARNING:suggestions.views:No valid suggestion after one retry: "
                    "the answer used ids that are not in the wardrobe: 42, 99"
                )
            ],
        )
        self.assertIsNone(logs.records[0].exc_info)


class PromptTests(SimpleTestCase):
    def test_prompt_lists_every_item_with_id_and_attributes(self):
        _, user = service.build_prompt(LISBON_FORECAST, WARDROBE)
        self.assertIn(
            "Wardrobe:\n"
            "- id 14: accessory — Grey scarf, colour Grey, material wool, warmth 4, "
            "not waterproof, not layerable\n"
            "- id 9: bottom — Blue jeans, colour Blue, material denim, warmth 3, "
            "not waterproof, not layerable\n"
            "- id 7: outer layer — Navy wool coat, colour Navy, material wool, "
            "warmth 5, not waterproof, not layerable\n"
            "- id 12: shoes — Leather boots, colour Brown, material leather, "
            "warmth 3, waterproof, not layerable\n"
            "- id 3: top — White T-shirt, colour White, material cotton, warmth 1, "
            "not waterproof, layerable\n",
            user,
        )

    def test_prompt_includes_forecast_values(self):
        _, user = service.build_prompt(LISBON_FORECAST, WARDROBE)
        self.assertIn(
            "Today's forecast (2026-11-10):\n"
            "- Temperature 13.4–19.5 °C, feels like 11.7–18.2 °C\n"
            "- Chance of rain 60%, max wind 25.3 km/h\n",
            user,
        )
        # As on the today page, a whole number has no decimal place.
        forecast = dataclasses.replace(
            LISBON_FORECAST, temperature_min=13.0, wind_max=25.0
        )
        _, user = service.build_prompt(forecast, WARDROBE)
        self.assertIn("- Temperature 13–19.5 °C,", user)
        self.assertIn("max wind 25 km/h", user)

    def test_prompt_does_not_include_city_name(self):
        prompt = "\n".join(service.build_prompt(LISBON_FORECAST, WARDROBE))
        self.assertNotIn("Lisbon", prompt)
        self.assertNotIn("Portugal", prompt)

    def test_prompt_does_not_include_size(self):
        prompt = "\n".join(service.build_prompt(LISBON_FORECAST, WARDROBE))
        for item in WARDROBE:
            with self.subTest(size=item.size):
                self.assertNotIn(item.size, prompt)
        self.assertNotIn("size", prompt.lower())

    def test_user_message_has_forecast_wardrobe_and_task_sections(self):
        system, user = service.build_prompt(LISBON_FORECAST, [SHIRT])
        self.assertEqual(system, service.SYSTEM_PROMPT)
        self.assertEqual(
            user,
            "Today's forecast (2026-11-10):\n"
            "- Temperature 13.4–19.5 °C, feels like 11.7–18.2 °C\n"
            "- Chance of rain 60%, max wind 25.3 km/h\n"
            "\n"
            "Wardrobe:\n"
            "- id 3: top — White T-shirt, colour White, material cotton, warmth 1, "
            "not waterproof, layerable\n"
            "\n"
            "Suggest an outfit using only the ids above.",
        )

    def test_system_prompt_states_the_rules(self):
        system, _ = service.build_prompt(LISBON_FORECAST, WARDROBE)
        # Key phrases rather than the whole text, so the wording can be tuned.
        for phrase in [
            "using only their ids",
            "feels-like temperature, chance of rain and wind",
            "warmth, waterproof and layerable",
            "1 (very light) to 5 (very warm)",
            "one bottom, one pair of shoes",
            "say so in the reason",
            "Use British English.",
        ]:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, system)


class ValidationTests(SimpleTestCase):
    def test_valid_response_returns_items_in_order(self):
        suggestion = service.parse_suggestion(VALID_ANSWER, ITEMS_BY_ID)
        # The LLM's order, not the wardrobe's.
        self.assertEqual(
            suggestion,
            service.Suggestion(items=(JEANS, SHIRT, COAT, BOOTS), reason=REASON),
        )

    def test_unknown_item_is_rejected(self):
        # The whole answer is rejected, not only the unknown ids.
        self.assertEqual(
            rejection_message({"item_ids": [9, 42, 3, 12, 99], "reason": REASON}),
            "used ids that are not in the wardrobe: 42, 99",
        )

    def test_empty_item_list_is_rejected(self):
        self.assertEqual(
            rejection_message({"item_ids": [], "reason": REASON}), "chose no items"
        )

    def test_duplicate_item_is_rejected(self):
        self.assertEqual(
            rejection_message({"item_ids": [9, 3, 9, 12, 3, 9], "reason": REASON}),
            "repeated ids: 9, 3",
        )

    def test_missing_reason_is_rejected(self):
        answers: list[dict[str, Any]] = [
            {"item_ids": [9, 3]},
            {"item_ids": [9, 3], "reason": None},
            {"item_ids": [9, 3], "reason": ""},
            {"item_ids": [9, 3], "reason": "   "},
        ]
        for answer in answers:
            with self.subTest(answer=answer):
                self.assertEqual(rejection_message(answer), "gave no reason")

    def test_item_ids_must_be_a_list_of_integers(self):
        # JSON true loads as True, which Python would treat as the id 1.
        answers: list[dict[str, Any]] = [
            {"reason": REASON},
            {"item_ids": None, "reason": REASON},
            {"item_ids": "9, 3", "reason": REASON},
            {"item_ids": 9, "reason": REASON},
            {"item_ids": [9, "3"], "reason": REASON},
            {"item_ids": [9, 3.0], "reason": REASON},
            {"item_ids": [9, True], "reason": REASON},
        ]
        for answer in answers:
            with self.subTest(answer=answer):
                self.assertEqual(
                    rejection_message(answer),
                    "did not give item_ids as a list of integers",
                )


@mock.patch("suggestions.llm.complete_json")
class SuggestOutfitTests(SimpleTestCase):
    def setUp(self):
        self.system, self.user = service.build_prompt(LISBON_FORECAST, WARDROBE)

    def test_sends_prompt_and_schema_and_returns_suggestion(self, complete_json):
        complete_json.return_value = VALID_ANSWER
        suggestion = service.suggest_outfit(LISBON_FORECAST, WARDROBE)
        self.assertEqual(
            suggestion,
            service.Suggestion(items=(JEANS, SHIRT, COAT, BOOTS), reason=REASON),
        )
        complete_json.assert_called_once_with(self.system, self.user, RESPONSE_SCHEMA)

    def test_retries_once_after_invalid_response(self, complete_json):
        complete_json.side_effect = [
            {"item_ids": [9, 3, 42, 12, 99], "reason": REASON},
            VALID_ANSWER,
        ]
        suggestion = service.suggest_outfit(LISBON_FORECAST, WARDROBE)
        self.assertEqual(suggestion.items, (JEANS, SHIRT, COAT, BOOTS))
        # The retry adds one line naming the problem to the user message.
        retry = (
            f"{self.user}\n\n"
            "Your previous answer used ids that are not in the wardrobe: 42, 99."
        )
        self.assertEqual(
            complete_json.call_args_list,
            [
                mock.call(self.system, self.user, RESPONSE_SCHEMA),
                mock.call(self.system, retry, RESPONSE_SCHEMA),
            ],
        )

    def test_gives_up_after_second_invalid_response(self, complete_json):
        complete_json.side_effect = [
            {"item_ids": [9, 42], "reason": REASON},
            {"item_ids": [], "reason": REASON},
        ]
        with self.assertRaises(service.InvalidSuggestion) as raised:
            service.suggest_outfit(LISBON_FORECAST, WARDROBE)
        self.assertEqual(str(raised.exception), "chose no items")
        self.assertEqual(complete_json.call_count, 2)

    def test_llm_error_propagates(self, complete_json):
        error = llm.LLMError("the Anthropic API timed out")
        complete_json.side_effect = error
        with self.assertRaises(llm.LLMError) as raised:
            service.suggest_outfit(LISBON_FORECAST, WARDROBE)
        self.assertIs(raised.exception, error)
        complete_json.assert_called_once()
        # An LLMError from the retry is not retried either.
        complete_json.reset_mock()
        complete_json.side_effect = [{"item_ids": [42], "reason": REASON}, error]
        with self.assertRaises(llm.LLMError) as raised:
            service.suggest_outfit(LISBON_FORECAST, WARDROBE)
        self.assertIs(raised.exception, error)
        self.assertEqual(complete_json.call_count, 2)


# The key is fake, and the client is a mock: nothing is sent.
@mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
@mock.patch("suggestions.llm.anthropic.Anthropic")
class LLMModuleTests(SimpleTestCase):
    def llm_error(self) -> llm.LLMError:
        """Call complete_json, which must raise LLMError; return the error."""
        with self.assertRaises(llm.LLMError) as raised:
            llm.complete_json("System prompt", "User prompt", ANSWER_SCHEMA)
        return raised.exception

    def test_returns_parsed_json_from_text_block(self, Anthropic):
        create = Anthropic.return_value.messages.create
        create.return_value = fake_message('{"answer": "yes"}')
        self.assertEqual(
            llm.complete_json("System prompt", "User prompt", ANSWER_SCHEMA),
            {"answer": "yes"},
        )

    @override_settings(LLM_MODEL="claude-sonnet-5-5")
    def test_sends_prompt_and_schema_to_configured_model(self, Anthropic):
        create = Anthropic.return_value.messages.create
        create.return_value = fake_message('{"answer": "yes"}')
        llm.complete_json("System prompt", "User prompt", ANSWER_SCHEMA)
        Anthropic.assert_called_once_with(
            api_key="test-key", timeout=30.0, max_retries=1
        )
        # Only these parameters: no thinking, effort or temperature.
        create.assert_called_once_with(
            model="claude-sonnet-5-5",
            max_tokens=16000,
            system="System prompt",
            messages=[{"role": "user", "content": "User prompt"}],
            output_config={"format": {"type": "json_schema", "schema": ANSWER_SCHEMA}},
        )

    def test_missing_key_is_llm_error(self, Anthropic):
        with mock.patch.dict(os.environ):
            del os.environ["ANTHROPIC_API_KEY"]
            self.assertEqual(str(self.llm_error()), "ANTHROPIC_API_KEY is not set")
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
            self.assertEqual(str(self.llm_error()), "ANTHROPIC_API_KEY is not set")
        # No client was created.
        Anthropic.assert_not_called()

    def test_sdk_error_becomes_llm_error(self, Anthropic):
        create = Anthropic.return_value.messages.create
        for error, message in [
            (
                anthropic.APIConnectionError(request=MESSAGES_REQUEST),
                "the Anthropic API could not be reached",
            ),
            (
                anthropic.APITimeoutError(request=MESSAGES_REQUEST),
                "the Anthropic API timed out",
            ),
            (
                status_error(
                    anthropic.AuthenticationError,
                    401,
                    "authentication_error",
                    "invalid x-api-key",
                ),
                "the Anthropic API returned an error (HTTP 401)",
            ),
            (
                status_error(
                    anthropic.OverloadedError, 529, "overloaded_error", "Overloaded"
                ),
                "the Anthropic API returned an error (HTTP 529)",
            ),
            (
                anthropic.APIResponseValidationError(
                    httpx2.Response(200, request=MESSAGES_REQUEST), None
                ),
                INVALID_RESPONSE,
            ),
        ]:
            with self.subTest(error=type(error).__name__):
                create.side_effect = error
                exc = self.llm_error()
                # A fixed message: the SDK's own one can quote the response body.
                self.assertEqual(str(exc), message)
                self.assertIs(exc.__cause__, error)

    def test_unexpected_stop_reason_is_llm_error(self, Anthropic):
        create = Anthropic.return_value.messages.create
        # Thinking used up max_tokens before the answer was finished.
        create.return_value = fake_message('{"answer": "y', stop_reason="max_tokens")
        self.assertEqual(str(self.llm_error()), "the model stopped early (max_tokens)")
        create.return_value = fake_message(None, stop_reason="refusal")
        self.assertEqual(str(self.llm_error()), "the model stopped early (refusal)")

    def test_invalid_json_is_llm_error(self, Anthropic):
        create = Anthropic.return_value.messages.create
        for text in [
            "Jeans and boots, in case of rain.",
            "",
            '{"answer": "yes"',
            '["yes"]',  # valid JSON, but not an object
            None,  # no text block, only the thinking block
        ]:
            with self.subTest(text=text):
                create.return_value = fake_message(text)
                self.assertEqual(str(self.llm_error()), INVALID_RESPONSE)

    def test_malformed_response_body_is_llm_error(self, Anthropic):
        create = Anthropic.return_value.messages.create
        # With HTTP 200, the SDK raises JSONDecodeError for a body that is not
        # valid JSON...
        create.side_effect = json.JSONDecodeError(
            "Expecting property name enclosed in double quotes", "{not json", 1
        )
        self.assertEqual(str(self.llm_error()), INVALID_RESPONSE)
        # ...and returns the text for a body that is not JSON at all.
        create.side_effect = None
        create.return_value = "<html>Blocked by a proxy</html>"
        self.assertEqual(str(self.llm_error()), INVALID_RESPONSE)


# Made up, and distinctive enough to be found if it leaked.
FAKE_KEY = "test-key-5f0c2a9e"


# Only the forecast and the SDK's client are replaced: the view, the service
# and the LLM module run as they are. Nothing is sent.
@mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": FAKE_KEY})
@mock.patch("weather.client.get_today_forecast", return_value=LISBON_FORECAST)
@mock.patch("suggestions.llm.anthropic.Anthropic")
class EndToEndTests(TestCase):
    def test_valid_answer_reaches_the_page(self, Anthropic, get_today_forecast):
        save_wardrobe()
        create = Anthropic.return_value.messages.create
        create.return_value = fake_message(json.dumps(VALID_ANSWER))
        response = self.client.post(reverse("suggestions:today"))
        # The prompt lists the saved wardrobe with its ids...
        _, user = service.build_prompt(LISBON_FORECAST, WARDROBE)
        self.assertEqual(
            create.call_args.kwargs["messages"], [{"role": "user", "content": user}]
        )
        # ...and the ids in the answer bring back the saved items, in the
        # answer's order, shown with the reason.
        self.assertEqual(
            [item.name for item in response.context["suggestion"].items],
            ["Blue jeans", "White T-shirt", "Navy wool coat", "Leather boots"],
        )
        self.assertContains(response, f"<p>{REASON}</p>", html=True)

    def test_key_appears_in_no_page_or_log_line(self, Anthropic, get_today_forecast):
        save_wardrobe()
        # The worst case: the provider's error message quotes the key.
        Anthropic.return_value.messages.create.side_effect = status_error(
            anthropic.AuthenticationError,
            401,
            "authentication_error",
            f"invalid x-api-key: {FAKE_KEY}",
        )
        # Every logger, not only the view's; a traceback attached to a line
        # would be part of its output.
        with self.assertLogs() as logs:
            response = self.client.post(reverse("suggestions:today"))
        # The LLM module ran, with the key from the environment.
        Anthropic.assert_called_once_with(api_key=FAKE_KEY, timeout=30.0, max_retries=1)
        self.assertContains(
            response,
            "<p>The suggestion service is unavailable right now.</p>",
            html=True,
        )
        self.assertNotIn(FAKE_KEY.encode(), response.content)
        self.assertNotIn(FAKE_KEY, "\n".join(logs.output))
