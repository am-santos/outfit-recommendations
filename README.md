# What should I wear today?

A personal web app that answers one question each morning: **what should I wear today?**

It combines today's weather forecast with the clothes I own, and it adjusts to my feedback. If yesterday's outfit felt too cold, too warm or not waterproof enough, tomorrow's suggestion takes that into account.

> **Status:** proof of concept. The wardrobe, today's forecast and LLM outfit suggestions work locally. Daily feedback comes next (see the [roadmap](#roadmap)).

## Scope

- **Single-user.** Built for one person (me). There are no sign-ups, accounts or other users.
- **Location is a city setting** (e.g. Lisbon), not GPS or an address.
- **Personal data: only my own.** The app stores my city, my wardrobe and my daily feedback. No other people's personal data is stored or processed.
- **Uses an existing LLM; no model training.** Outfit suggestions come from an existing, general-purpose LLM, called through its API with the weather forecast, the wardrobe and previous feedback. No model is trained or fine-tuned.

## Planned features

### 1. Wardrobe
Add, edit and remove clothing items, each with generic attributes, for example:
- **Type:** top, bottom, outer layer, shoes, accessory
- **Colour**
- **Size**
- **Material:** cotton, wool, denim, synthetic…
- **Warmth level:** 1 (very light) to 5 (very warm)
- **Waterproof:** yes / no
- **Layerable:** yes / no

This list is a starting point. More attributes will be added as they are needed.

### 2. Forecast
Fetch today's forecast for one configured city: temperature, feels-like temperature, chance of rain and wind.

### 3. Outfit suggestion
Send today's forecast, the wardrobe and previous feedback to the LLM, and get back an outfit made only from items I own. The response is checked against the wardrobe before it is shown, and any item that isn't in the wardrobe is rejected. Each suggestion says *why* it was chosen.

### 4. Daily feedback
At the end of the day, or the next morning, the app asks how the day's outfit felt: **too warm / just right / too cold / got wet**.

### 5. Suggestions that use past feedback
- A **history** of past days: forecast, outfit worn and feedback.
- Feedback from past days with a similar forecast (for example, within a few degrees of today's feels-like temperature) is included with each new suggestion request, so the suggestions adapt over time. If I often felt cold at 12 °C, the next 12 °C day gets a warmer outfit.
- Nothing is trained; the history is only used as context for the LLM.

## Future scope

### Add clothes from a photo
Add a new item to the wardrobe by uploading a photo of it. The LLM reads the image and fills in the item's attributes, which I confirm or correct before saving.

### Log today's outfit from a photo
Log today's outfit by uploading a photo of the clothes. The LLM reads the image and matches it to items already in my wardrobe, which I confirm before saving.

Photos are of my own clothes. They are sent straight to the LLM API for analysis and are not stored by the app.

### Dedicated frontend
A Next.js (TypeScript) frontend, so the morning check works well on a phone. It consumes a REST API exposed by the Django app and replaces the Django templates.

### PostgreSQL
Move the database from SQLite to PostgreSQL once the app is deployed to a host where a SQLite file would not persist.

## Planned tech stack

| Area | PoC / MVP | Later |
|---|---|---|
| Language | Python 3.12 | Python 3.12, plus TypeScript for the frontend |
| Framework | Django (backend **and** frontend) | Django (backend and REST API) |
| Frontend | Server-rendered Django templates and forms | Next.js, consuming the Django REST API |
| Database | SQLite | PostgreSQL |
| Outfit suggestions | An LLM via its API (Anthropic Claude, Haiku 5.5) | Same; also used to read clothing and outfit photos |
| Weather data | Open-Meteo (free, no API key; provides temperature, feels-like, chance of rain and wind) | Same |
| Dependencies | uv | uv |
| Tests | Django's test framework | Django's test framework |
| Linting and types | Ruff; mypy in strict mode with django-stubs | Same |

## Roadmap

1. **Proof of concept:** wardrobe (1), forecast (2) and LLM outfit suggestion (3), all in Django.
2. **MVP:** daily feedback (4) and suggestions that use past feedback (5).
3. **Later:** adding clothes and logging outfits from photos, the REST API and Next.js frontend, and the move to PostgreSQL.

## Run locally

You need [uv](https://docs.astral.sh/uv/). From the repository root:

1. `uv sync` installs the dependencies.
2. `cp .env.example .env`, then fill in `.env`; no `manage.py` command runs without it. Set `DJANGO_SECRET_KEY` to the output of `uv run python -c "import secrets; print(secrets.token_urlsafe(50))"`, and put your Anthropic API key in `ANTHROPIC_API_KEY`.
3. `uv run manage.py migrate` creates the SQLite database.
4. `uv run manage.py runserver` serves the app at <http://127.0.0.1:8000/>.
5. `uv run manage.py test` runs the tests, which need no network access or API key.

Code checks: `uv run ruff check`, `uv run ruff format --check` and `uv run mypy .`

## Ownership and licence

Personal side project, solely owned and developed by me, António Santos ([am-santos](https://github.com/am-santos) on GitHub). There are no other maintainers or contributors.

Licensed under the MIT License. See [LICENSE](LICENSE).
