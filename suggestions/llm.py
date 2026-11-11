"""The LLM provider, Anthropic (Claude), behind one function: complete_json.

Everything provider-specific lives here, so changing provider means rewriting
this module and nothing else. The API key is read from the environment on each
call; it is never put in settings, printed or logged, and Django's error pages
hide it. Every failure becomes an LLMError whose message is short and safe to
show.
"""

import json
import os
from typing import Any

import anthropic
from django.conf import settings
from django.views.decorators.debug import sensitive_variables

# Thinking tokens count towards this limit, so it leaves room for them as well
# as the answer.
MAX_TOKENS = 16000

# Seconds to wait for each attempt. The SDK retries timeouts, rate limits and
# server errors once.
TIMEOUT = 30.0
MAX_RETRIES = 1

INVALID_RESPONSE = "the Anthropic API sent an invalid response"


class LLMError(Exception):
    """The LLM gave no usable answer.

    The message is short and safe to show: it never includes the API key,
    request headers or a response body.
    """


# With no names given, Django's error pages hide every variable of this
# function and of every function it calls, so the SDK's frames, which hold the
# key, are hidden too. config.error_reports makes this work when DEBUG is True.
@sensitive_variables()
def complete_json(system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
    """Send a prompt, return the parsed JSON object. Raises LLMError.

    The answer is constrained to the JSON schema given.
    """
    key = os.environ.get("ANTHROPIC_API_KEY")
    # Unset, the SDK would fall back to other credentials; empty, it would send
    # an empty key.
    if not key:
        raise LLMError("ANTHROPIC_API_KEY is not set")
    client = anthropic.Anthropic(api_key=key, timeout=TIMEOUT, max_retries=MAX_RETRIES)
    try:
        response = client.messages.create(
            model=settings.LLM_MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
    except anthropic.APITimeoutError as exc:
        raise LLMError("the Anthropic API timed out") from exc
    except anthropic.APIConnectionError as exc:
        raise LLMError("the Anthropic API could not be reached") from exc
    except anthropic.APIStatusError as exc:
        # The error's own message quotes the response body: only the status
        # is passed on.
        raise LLMError(
            f"the Anthropic API returned an error (HTTP {exc.status_code})"
        ) from exc
    except anthropic.APIError as exc:
        raise LLMError(INVALID_RESPONSE) from exc
    except json.JSONDecodeError as exc:
        # Raised by the SDK, instead of an APIError, when a response with HTTP
        # 200 has a body that is not valid JSON.
        raise LLMError(INVALID_RESPONSE) from exc
    # When the body is not JSON at all, the SDK returns it as text.
    if not isinstance(response, anthropic.types.Message):
        raise LLMError(INVALID_RESPONSE)
    if response.stop_reason != "end_turn":
        # For example max_tokens, or refusal.
        raise LLMError(f"the model stopped early ({response.stop_reason})")
    # The answer can come after one or more thinking blocks.
    text = next(
        (
            block.text
            for block in response.content
            if isinstance(block, anthropic.types.TextBlock)
        ),
        None,
    )
    if text is None:
        raise LLMError(INVALID_RESPONSE)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError(INVALID_RESPONSE) from exc
    if not isinstance(data, dict):
        raise LLMError(INVALID_RESPONSE)
    return data
