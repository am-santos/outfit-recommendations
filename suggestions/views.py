import logging
from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.views.generic import TemplateView

from suggestions import llm, service
from wardrobe import models
from weather import client

logger = logging.getLogger(__name__)


class TodayView(TemplateView):
    """Today's forecast and the wardrobe; a POST adds an outfit suggestion.

    The Suggest form posts to this same page, which shows the suggestion.
    Nothing is stored, and a GET never shows a suggestion.
    """

    template_name = "suggestions/today.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        try:
            context["forecast"] = client.get_today_forecast(settings.CITY)
        except client.WeatherError as exc:
            # Only the short message and the class of the original exception
            # are logged: no traceback, and no request URL.
            cause = exc.__cause__ or exc
            logger.warning("Forecast unavailable: %s (%s)", exc, type(cause).__name__)
            context["forecast"] = None
            context["weather_error"] = str(exc)
        context["item_count"] = models.ClothingItem.objects.count()
        return context

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        # The forecast is fetched again, for the page and for the suggestion.
        context = self.get_context_data(**kwargs)
        forecast: client.Forecast | None = context["forecast"]
        items = list(models.ClothingItem.objects.all())
        # With no forecast or no clothes, the page is the same as for a GET and
        # the LLM is not called.
        if forecast is None or not items:
            return self.render_to_response(context)
        try:
            context["suggestion"] = service.suggest_outfit(forecast, items)
        except service.InvalidSuggestion as exc:
            # The page shows a fixed message; the log says what was wrong.
            logger.warning("No valid suggestion after one retry: the answer %s", exc)
            context["suggestion_rejected"] = True
        except llm.LLMError as exc:
            # As for the forecast: the short message and the class of the
            # original exception, with no traceback.
            cause = exc.__cause__ or exc
            logger.warning(
                "Suggestion service unavailable: %s (%s)", exc, type(cause).__name__
            )
            context["suggestion_unavailable"] = True
        return self.render_to_response(context)
