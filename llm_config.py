"""Single place for which LLM the app uses and how to reach it.

Shared by the Streamlit app (jd_analyzer.py, resume_analyzer.py, app.py) and
the standalone API backend (api.py), so changing the model is a one-line edit
here. See docs/MODEL_COMPARISON.md for why this is gpt-6-luna at medium effort.

Deliberately does not import streamlit at module level: api.py runs outside
Streamlit and has no st.secrets.
"""
import os

from openai import OpenAI

LLM_MODEL = "gpt-6-luna"
REASONING_EFFORT = "medium"


def get_client(api_key=None):
    """Build an OpenAI client. Key lookup order: explicit arg, OPENAI_API_KEY
    env var (Render/api.py), then st.secrets["openai-key"] (Streamlit)."""
    if api_key is None:
        api_key = os.environ.get("OPENAI_API_KEY")
    if api_key is None:
        import streamlit as st
        api_key = st.secrets["openai-key"]["OPENAI_API_KEY"]
    return OpenAI(api_key=api_key)
