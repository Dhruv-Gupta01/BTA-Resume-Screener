"""Single place for which LLM the app uses and how to reach it.

Shared by the Streamlit app (jd_analyzer.py, resume_analyzer.py, app.py) and
the standalone API backend (api.py), so changing the model is a one-line edit
here. See docs/MODEL_COMPARISON.md for the earlier model comparison; the app
moved from gpt-6-luna to Claude Haiku 5.5 (same price: $0.10 / $0.50 per 1M tokens).

Deliberately does not import streamlit at module level: api.py runs outside
Streamlit and has no st.secrets.
"""
import os
import re
from types import SimpleNamespace

import anthropic

LLM_MODEL = "claude-haiku-5-5"
REASONING_EFFORT = "medium"

# Thinking tokens count against max_tokens on Claude, so the 4096 the call sites
# were written with (OpenAI's max_completion_tokens) is raised to this floor.
MIN_MAX_TOKENS = 8000


class _ChatCompletions:
    """Lets the existing `client.chat.completions.create(...)` call sites keep their
    OpenAI-style shape while the request goes to the Anthropic Messages API.

    - system message -> `system`, the rest -> `messages`
    - `reasoning_effort` -> `output_config.effort`
    - `response_format` is dropped: the prompts already say "output ONLY the JSON
      object"; stray ```json fences are stripped from the reply before it is returned
    - returns an object with `.choices[0].message.content`, like the OpenAI SDK
    """

    def __init__(self, client):
        self._client = client

    def create(self, model, messages, response_format=None, reasoning_effort=None,
               max_completion_tokens=None, **_ignored):
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        turns = [m for m in messages if m["role"] != "system"]
        kwargs = {}
        if system:
            kwargs["system"] = system
        if reasoning_effort:
            kwargs["output_config"] = {"effort": reasoning_effort}
        response = self._client.messages.create(
            model=model,
            max_tokens=max(max_completion_tokens or 0, MIN_MAX_TOKENS),
            messages=turns,
            **kwargs,
        )
        text = "".join(b.text for b in response.content if b.type == "text").strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
        message = SimpleNamespace(content=text)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=response.usage)


def get_client(api_key=None):
    """Build a client exposing `.chat.completions.create`. Key lookup order: explicit
    arg, ANTHROPIC_API_KEY env var (Render/api.py), then
    st.secrets["anthropic-key"]["ANTHROPIC_API_KEY"] (Streamlit)."""
    if api_key is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key is None:
        import streamlit as st
        api_key = st.secrets["anthropic-key"]["ANTHROPIC_API_KEY"]
    client = anthropic.Anthropic(api_key=api_key)
    return SimpleNamespace(chat=SimpleNamespace(completions=_ChatCompletions(client)))
