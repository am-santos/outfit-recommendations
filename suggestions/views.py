import logging
from typing import Any

from django.conf import settings
from django.views.generic import TemplateView

from wardrobe import models
from weather import client

logger = logging.getLogger(__name__)


class TodayView(TemplateView):
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
