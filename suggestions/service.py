"""Today's outfit suggestion: the prompt, the LLM call and the answer's checks.

The LLM is shown the forecast and the wardrobe, and answers with the ids of
the items it chose and a reason. The answer is checked against the wardrobe
before it is used; an invalid answer gets one retry.
"""

import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from suggestions import llm
from wardrobe import models
from weather import client

# The shape of the LLM's answer. Non-empty, no duplicates and "every id is
# owned" are checked by parse_suggestion, not by the schema.
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "item_ids": {"type": "array", "items": {"type": "integer"}},
        "reason": {"type": "string"},
    },
    "required": ["item_ids", "reason"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "You suggest one outfit for today from the wardrobe items listed, using only "
    "their ids. Consider the feels-like temperature, chance of rain and wind, and "
    "each item's warmth, waterproof and layerable attributes. Warmth runs from 1 "
    "(very light) to 5 (very warm). Choose one bottom, one pair of shoes, one or "
    "more tops or outer layers as needed, and accessories if useful. Answer with "
    "the chosen ids in item_ids and a short explanation of the choice in reason. "
    "The user sees the reason but not the ids, so in the reason refer to items "
    "by name, never by id. If the wardrobe cannot cover the weather, say so in "
    'the reason, for example "you have no waterproof layer". Use British English.'
)

# An id from the wardrobe list in brackets, as the LLM may still quote it after
# an item's name: "(18)", "(id 18)", "(ID: 18)" or "(#18)", with the space
# before it.
QUOTED_ID = re.compile(r"[ \t]*\(\s*(?:id\s*:?|#)?\s*(\d+)\s*\)", re.IGNORECASE)


class InvalidSuggestion(Exception):
    """The LLM's answer is not a valid outfit from the wardrobe.

    The message names the problem in words that follow "Your previous answer",
    so that it can be sent back to the LLM.
    """


@dataclass(frozen=True)
class Suggestion:
    items: tuple[models.ClothingItem, ...]  # in the order the LLM gave them
    reason: str


def suggest_outfit(
    forecast: client.Forecast, items: Iterable[models.ClothingItem]
) -> Suggestion:
    """Ask the LLM for an outfit from the items for the forecast.

    An invalid answer is retried once, with a line naming the problem added to
    the user message; a second invalid answer raises InvalidSuggestion. An
    LLMError is not retried here: the SDK has already retried the request.
    """
    items = list(items)
    items_by_id = {item.pk: item for item in items}
    system, user = build_prompt(forecast, items)
    try:
        return parse_suggestion(llm.complete_json(system, user, SCHEMA), items_by_id)
    except InvalidSuggestion as exc:
        problem = str(exc)
    # One retry, with a line naming the problem at the end of the user message.
    user = f"{user}\n\nYour previous answer {problem}."
    return parse_suggestion(llm.complete_json(system, user, SCHEMA), items_by_id)


def build_prompt(
    forecast: client.Forecast, items: Iterable[models.ClothingItem]
) -> tuple[str, str]:
    """Return the system and user messages for the forecast and the items.

    The user message is built in sections: forecast, wardrobe, then the task.
    The city and each item's size do not change what suits the weather, so
    they are not sent.
    """
    sections = [
        _forecast_section(forecast),
        _wardrobe_section(items),
        "Suggest an outfit using only the ids above.",
    ]
    return SYSTEM_PROMPT, "\n\n".join(sections)


def parse_suggestion(
    data: dict[str, Any], items_by_id: Mapping[int, models.ClothingItem]
) -> Suggestion:
    """Check the LLM's answer against the wardrobe and return the suggestion.

    Any problem rejects the whole answer with InvalidSuggestion: an outfit with
    an unknown item left out could be missing its trousers. Any wardrobe id
    the reason quotes is removed from it, as the page shows items by name.
    """
    item_ids = data.get("item_ids")
    # An exact type check: JSON true and false load as bool, a subclass of int.
    if not isinstance(item_ids, list) or not all(type(i) is int for i in item_ids):
        raise InvalidSuggestion("did not give item_ids as a list of integers")
    if not item_ids:
        raise InvalidSuggestion("chose no items")
    repeated = [i for i, count in Counter(item_ids).items() if count > 1]
    if repeated:
        raise InvalidSuggestion(f"repeated ids: {_list_ids(repeated)}")
    unknown = [i for i in item_ids if i not in items_by_id]
    if unknown:
        raise InvalidSuggestion(
            f"used ids that are not in the wardrobe: {_list_ids(unknown)}"
        )
    reason = data.get("reason")
    if isinstance(reason, str):
        reason = _without_ids(reason, items_by_id)
    if not isinstance(reason, str) or not reason.strip():
        raise InvalidSuggestion("gave no reason")
    return Suggestion(items=tuple(items_by_id[i] for i in item_ids), reason=reason)


def _without_ids(reason: str, items_by_id: Mapping[int, models.ClothingItem]) -> str:
    """The reason without the wardrobe ids it quotes; other brackets stay."""
    return QUOTED_ID.sub(lambda m: "" if int(m[1]) in items_by_id else m[0], reason)


def _forecast_section(forecast: client.Forecast) -> str:
    temperature = (
        f"{_number(forecast.temperature_min)}–{_number(forecast.temperature_max)} °C"
    )
    feels_like = (
        f"{_number(forecast.feels_like_min)}–{_number(forecast.feels_like_max)} °C"
    )
    wind = f"{_number(forecast.wind_max)} km/h"
    return "\n".join(
        [
            f"Today's forecast ({forecast.date.isoformat()}):",
            f"- Temperature {temperature}, feels like {feels_like}",
            f"- Chance of rain {forecast.rain_chance}%, max wind {wind}",
        ]
    )


def _wardrobe_section(items: Iterable[models.ClothingItem]) -> str:
    lines = ["Wardrobe:"]
    for item in items:
        # The name is free text and can repeat the colour or material, so
        # those are sent as labelled attributes.
        attributes = [
            item.name,
            f"colour {item.colour}",
            f"material {item.get_material_display().lower()}",
            f"warmth {item.warmth}",
            "waterproof" if item.waterproof else "not waterproof",
            "layerable" if item.layerable else "not layerable",
        ]
        category = item.get_category_display().lower()
        lines.append(f"- id {item.pk}: {category} — {', '.join(attributes)}")
    return "\n".join(lines)


def _number(value: float) -> str:
    """One decimal place at most, and none for a whole number, as on the page."""
    return f"{value:.1f}".removesuffix(".0")


def _list_ids(ids: Iterable[int]) -> str:
    return ", ".join(str(i) for i in ids)
