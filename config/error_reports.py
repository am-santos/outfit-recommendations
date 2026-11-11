"""Django's error reports, with sensitive variables hidden even when DEBUG is on.

Django hides the variables marked with @sensitive_variables, and the POST
parameters marked with @sensitive_post_parameters, only when DEBUG is False.
The app runs locally with DEBUG on, so without this filter Django's debug page
would show the Anthropic API key held by suggestions.llm.complete_json.
"""

from django.http import HttpRequest
from django.views.debug import SafeExceptionReporterFilter


class AlwaysActiveFilter(SafeExceptionReporterFilter):
    """Django's filter, active whatever the value of DEBUG."""

    def is_active(self, request: HttpRequest | None) -> bool:
        return True
