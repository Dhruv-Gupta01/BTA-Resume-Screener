# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Streamlit app that uses OpenAI models to compare candidate resumes against a job description, producing structured requirement matches, a qualitative assessment, a score, and a Yes/No recommendation. Built by Mercity-AI. See `README.md` for the full feature list and usage walkthrough.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run app.py

# Run the manual smoke test (calls the real OpenAI API against a hardcoded resume/JD)
python test_resume_analyzer.py

# Run the standalone CLI/Google Sheets batch script (prompts for JD on stdin)
python google_sheet_resume_analyzer.py
```

There is no linter or automated test suite configured — `test_resume_analyzer.py` is a manual script that prints LLM output for eyeballing, not a pytest suite, and it makes real, billed OpenAI API calls.

## Configuration / secrets

- Model and client: `llm_config.py` is the single place for the model (`LLM_MODEL = "gpt-6-luna"`), reasoning effort (`REASONING_EFFORT = "medium"`) and client construction (`get_client()`). `jd_analyzer.py`/`resume_analyzer.py`/`api.py` all go through it; change the model there, not at call sites. Rationale and test results: `docs/MODEL_COMPARISON.md`.
- OpenAI key: `get_client()` reads, in order, an explicit `api_key` arg, the `OPENAI_API_KEY` env var (used by `api.py` on Render), then `st.secrets["openai-key"]["OPENAI_API_KEY"]` (Streamlit, i.e. `.streamlit/secrets.toml`). Both the Streamlit Cloud Secrets and the Render env vars need the key.
- Google Sheets integration (`app.py` tab 2) reads a service account dict from `st.secrets["google_service_account"]` and authorizes via `oauth2client.service_account.ServiceAccountCredentials` + `gspread`.
- `google_sheet_resume_analyzer.py` is the older/standalone variant of the same sheet workflow and instead expects a local `service_account.json` file and a hardcoded sheet URL — it does not go through Streamlit secrets. `service_account_base64.txt` and `service_account.json` are gitignored; don't commit real credentials into them.

## Architecture

Three-stage pipeline, each stage a thin wrapper around one OpenAI chat-completions call with a fixed system prompt and a strict `response_format: json_object`:

1. **`jd_analyzer.py`** — `analyze_job_description(job_description, model)` sends the raw JD text to OpenAI and gets back a structured requirements JSON with four top-level keys: `original_job_description`, `must_have_requirements` (technical_skills, experience, qualifications, core_responsibilities), `good_to_have_requirements` (additional_skills, extra_qualifications, bonus_experience), and `additional_screening_criteria`. Also has `parse_edited_requirements(...)` to turn hand-edited text areas back into this JSON shape (used by the "edit requirements" flow in the UI).

2. **`resume_analyzer.py`** — `analyze_resume(resume_text, requirements, model)` is the core evaluator. Branches on whether `requirements` (the dict from step 1) was supplied:
   - **With JD**: does a boolean requirement-match check against every item in `requirements`, then a qualitative assessment (project gravity, ownership/initiative, transferability), then a final Yes/No recommendation. Returns `{"score": "X/Y", "analysis": {...}}`.
   - **Without JD**: falls back to a JD-less resume summary (skills, key projects, education, qualitative assessment, career trajectory) with no score/recommendation. Returns `{"score": "", "analysis": {...}}`.
   `calculate_score(analysis)` counts `True` values across every boolean field in `requirement_match` to build the `"X/Y"` score string — this only applies to the with-JD branch. Both branches expect the exact JSON shape spelled out in their system prompts; if you change the output schema, update both the prompt's example JSON and every place in `app.py`/`google_sheet_resume_analyzer.py` that reads specific keys out of `analysis`.

3. **`app.py`** — the Streamlit UI and orchestrator. No separate `main()`; the module runs top-to-bottom as a Streamlit script (reruns on every interaction, state lives in `st.session_state`). Key pieces:
   - File text extraction: `extract_text_from_pdf` (PyPDF2), `extract_text_from_docx` (python-docx), plain `.txt` decode — dispatched via `process_file`.
   - Two tabs: **Tab 1** ("Upload Resumes") — upload files directly, analyze each against `st.session_state.requirements`, render results, offer CSV export via `flatten_analysis_for_csv`. **Tab 2** ("Sheet-based Analysis") — given a Google Sheet URL + worksheet name + a column of Google Drive resume links, downloads each PDF, runs the same `analyze_resume`, and writes `Score`/`Final Decision`/`Decision Summary`/`Resume Summary`/`Skills` back into the sheet (skipping rows that already have a `Final Decision`).
   - A pile of `display_*`/`create_*` helper functions render the nested analysis JSON as custom HTML (dark-themed `<details>` elements, colored qualitative-factor badges, contact info cards) — these are tightly coupled to the exact key names in the JSON schema produced by `resume_analyzer.py`/`jd_analyzer.py`.
   - Model is fixed (`llm_config.LLM_MODEL`) and shown read-only in the sidebar; `st.session_state.selected_models` just carries it into `analyze_job_description`/`analyze_resume`. Reasoning models count thinking tokens against `max_completion_tokens`, and `temperature` is not set for that reason.

- **`google_sheet_resume_analyzer.py`** is a standalone CLI script duplicating the Tab-2 sheet workflow (imports `extract_text_from_pdf`/`extract_text_from_docx` from `app.py`, which means importing it will also execute `app.py`'s Streamlit page-config side effects). Treat it as legacy/alternate entry point, not code shared by `app.py`.

## Working with the JSON schemas

Almost every bug or feature here comes down to the JSON contracts between the three files. When changing a prompt's output schema in `jd_analyzer.py` or `resume_analyzer.py`, trace every consumer:
- `jd_analyzer.format_requirements_for_display` / `parse_edited_requirements`
- `resume_analyzer.calculate_score`
- `app.py`'s `display_simple_minimal_requirements`, `display_qualitative_assessment`, `flatten_analysis_for_csv`, and the Tab 2 sheet-writing block

These all assume specific nested keys exist and will silently produce empty/`N/A` output (or KeyErrors in the sheet flow) rather than erroring loudly if the schema drifts.
