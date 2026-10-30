# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A resume-screening platform that uses an OpenAI model (`gpt-6-luna`, medium reasoning effort) to compare candidate resumes against a job description. Originally built by Mercity-AI (see `README.md`, which is partly stale), now maintained at `Dhruv-Gupta01/BTA-Resume-Screener`.

It ships as **two deployments from one repo**:

1. **Streamlit UI** (`app.py`) - recruiters paste a JD, then either upload resumes (Tab 1) or point at a Google Sheet of resume links (Tab 2).
2. **FastAPI backend** (`api.py`) - a standalone HTTP API that scores resumes against a JD. Streamlit Tab 2 calls it, and external applications can call it directly.

## Platform at a glance

| Piece | File | Where it runs | What it does |
|---|---|---|---|
| Streamlit UI | `app.py` | Most likely Streamlit Community Cloud (URL not in the repo - confirm) | JD analysis, manual upload analysis, sheet-based scoring |
| Backend API | `api.py` | Render free web service, `https://bta-resume-screener.onrender.com` (service `BTA-Resume-Screener`, auto-deploys from `main`) | `/health`, `/score-resume`, `/score-resumes` |
| LLM config | `llm_config.py` | imported by all of the above | model, reasoning effort, OpenAI client |
| JD analyzer | `jd_analyzer.py` | in-process (Streamlit) | JD text -> structured requirements JSON |
| Resume analyzer | `resume_analyzer.py` | in-process (Streamlit Tab 1) and inside the Render API | resume -> analysis / score |

Data flow:
- **Tab 1 (manual upload)**: Streamlit process -> OpenAI directly (`analyze_job_description`, `analyze_resume`). Does not use the Render API.
- **Tab 2 (Google Sheet)**: Streamlit -> Google Sheets/Drive -> Streamlit extracts PDF text -> `POST /score-resume` on Render -> OpenAI -> result written back to the sheet.
- **External callers**: -> Render API (`X-API-Key`) -> OpenAI.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the Streamlit app (port 8501)
streamlit run app.py

# Run the backend API locally (needs OPENAI_API_KEY and BACKEND_API_KEY env vars)
uvicorn api:app --reload --port 8000

# Manual smoke test of the Tab-1 pipeline (real, billed OpenAI calls; prints output for eyeballing)
python test_resume_analyzer.py

# Legacy standalone Google Sheets script (see "Legacy files") - not maintained
python google_sheet_resume_analyzer.py
```

There is no linter or automated test suite. `test_resume_analyzer.py` is a manual script, not pytest. A `.devcontainer/` config exists for GitHub Codespaces (Python 3.11, runs `streamlit run app.py` on port 8501).

## Model and configuration

- **Model**: `llm_config.py` is the single place for `LLM_MODEL = "gpt-6-luna"`, `REASONING_EFFORT = "medium"` and `get_client()`. Change the model there, not at call sites. Why this model and effort: `docs/MODEL_COMPARISON.md` (switched 2026-10-30 from `gpt-oss-120b` on Fireworks).
- **Reasoning-model constraints**: thinking tokens count against `max_completion_tokens` (4096 in both `jd_analyzer.py` and the sheet analyzer), and `temperature` is deliberately not set. Do not reintroduce `max_tokens` / `temperature` without testing against the model.
- **Streamlit sidebar** shows the model read-only. `st.session_state.selected_models` just carries `LLM_MODEL` into the analyzers; there is no model picker anymore.

### Secrets and environment

| Secret | Used by | Where to set |
|---|---|---|
| `OPENAI_API_KEY` | all LLM calls | Streamlit: `[openai-key]` block in `.streamlit/secrets.toml` (local) or app Secrets (Cloud). Render: env var. |
| `BACKEND_API_KEY` | shared secret between Streamlit Tab 2 (and other callers) and the Render API, sent as `X-API-Key` | Streamlit: `[backend-key]` block. Render: env var. Any long random string, NOT the OpenAI key. |
| `google_service_account` | Tab 2 Google Sheets/Drive access | Streamlit: `[google_service_account]` block (service-account JSON fields) |

- `get_client()` resolves the OpenAI key in order: explicit `api_key` arg, `OPENAI_API_KEY` env var, then `st.secrets["openai-key"]["OPENAI_API_KEY"]`. `llm_config.py` imports streamlit lazily so `api.py` never touches it.
- `.streamlit/secrets.toml`, `.env`, `service_account.json` are gitignored. Never commit real credentials. `service_account_base64.txt` is tracked but empty - keep it that way.
- `secrets.toml` may still contain unused `[fireworks-key]` and `[groq-key]` blocks from earlier model providers; they can be deleted. Likewise `FIREWORKS_API_KEY` in Render.
- `load_dotenv()` is called in the analyzer modules but runtime keys come from `st.secrets` / env vars as above.

## Backend API (`api.py`)

Base URL (production): `https://bta-resume-screener.onrender.com`. FastAPI auto-docs are not disabled in code, so `/docs` should be available (not verified). CORS is open (`*`) because auth is by API key, not cookies. Free-tier Render instances spin down when idle; the first request after idle can take 50s or more.

**Auth**: all endpoints except `/health` require header `X-API-Key: <BACKEND_API_KEY>`. Missing/wrong key -> `401`. If the server has no `BACKEND_API_KEY` configured -> `500` (fails closed).

### `GET /health`
Unauthenticated liveness check. Returns `{"status": "ok", "openai_key_configured": true|false}`. Does not verify the key actually works.

### `POST /score-resume`
Score one resume against a JD.

Request:
```json
{
  "job_description": "string (required)",
  "resume_text": "string (required)",
  "criteria": [{"text": "4-7 years building production systems", "weight": 40}],
  "jd_weight": 30
}
```
- `criteria` (optional): weighted rubric. Each `weight` must be > 0; weights are normalized, no need to sum to 100.
- `jd_weight` (optional, default 0, >= 0): weight of the model's holistic "fit to the whole JD" judgment, treated as one more entry in the weighted average.

Response (`ResumeScoreResult`):
```json
{
  "skills": "comma-separated string",
  "strongest_language": "Java",
  "summary": "3-5 sentence recruiter-style summary",
  "score": 73,
  "criteria_breakdown": [{"criterion": "...", "weight": 40, "score": 85}]
}
```
`criteria_breakdown` is only present when `criteria` and/or `jd_weight` were used (the JD entry appears as "Overall fit to the job description as a whole"). Errors: `401` auth, `502` if the LLM analysis failed after retries, `422` for malformed request bodies.

### `POST /score-resumes`
Batch version: one JD, up to `MAX_BATCH_SIZE = 100` resumes.

Request:
```json
{
  "job_description": "string",
  "resumes": [{"id": "cand-1", "resume_text": "..."}],
  "criteria": [...],
  "jd_weight": 0
}
```
Response: `{"results": [{"id": "cand-1", "result": {...ResumeScoreResult...}, "error": null}]}` in the same order as the request. Resumes are scored concurrently (`MAX_CONCURRENT_CALLS = 15`); one failure does not fail the batch - that item comes back with `error` set and no `result`. `criteria` / `jd_weight` apply to every resume in the batch. Note a 100-resume batch can run long enough to hit proxy/request timeouts on a free Render instance.

## Streamlit app (`app.py`)

The module runs top-to-bottom on every interaction (no `main()`); state lives in `st.session_state`. Everything below is in `app.py`.

**Shared header**
- **Job Description expander**: paste JD text (`st.session_state.jd_input`), click "Analyze JD" to run `analyze_job_description` and store the structured result in `st.session_state.requirements`. Tab 1 requires this; Tab 2 only needs the raw `jd_input` text (the user must still click "Analyze JD" or press Cmd/Ctrl+Enter so the text registers in session state).
- **Sidebar**: read-only model name.

**Tab 1 - "Upload Resumes"**
- Upload any number of PDF / DOCX / TXT resumes (`extract_text_from_pdf` via PyPDF2, `extract_text_from_docx` via python-docx, plain decode, dispatched by `process_file`).
- Each is run through `analyze_resume(resume_text, requirements)` in-process (the with-JD branch).
- Per resume it shows, in an expander, the percentage (`calculate_percentage` turns the `"X/Y"` score into a %), contact info if present, the recruiter-style summary, and the Yes/No final recommendation, all via plain `st.write`.
- "Download Results as CSV" exports every analysis flattened by `flatten_analysis_for_csv` (one row per resume).
- Note: `app.py` defines many HTML-rendering and editing helpers (`display_simple_minimal_requirements`, `display_requirement_matches`, `display_qualitative_assessment`, `display_requirement_progress`, `display_contact_info`, `create_collapsible_section`, `create_details_element`, `format_requirements_for_editing`) and imports `format_requirements_for_display` / `parse_edited_requirements`, but none are currently called from the main flow. The requirements-editing UI is not wired up. Treat them as dormant, but keep them in mind if you change the schema.

**Tab 2 - "Sheet-based Analysis"**
- Inputs: Google Sheet URL, worksheet name (case-sensitive, default `Sheet1`), name of the column holding Google Drive resume links (default `Resume`), delay between resumes (default 3s, safety buffer for rate limits).
- Optional **Weighted Scoring Criteria** (`st.data_editor`, rows of Criterion + Weight) and **JD Weight**. Blank or zero-weight rows are dropped. With neither, the backend returns one holistic 0-100 score.
- For each row: skip if `AI: Score` is already filled or the link is empty; parse the Drive file ID (`id=` or `/d/<id>/` forms); download the PDF from `drive.google.com/uc?export=download`; extract text; `POST` to the Render `/score-resume` with `X-API-Key` (timeout 120s to allow the free instance to wake); write results to the sheet.
- Output columns (auto-created in row 1 if missing, grid expanded if needed): `AI: Skills`, `AI: Strongest Language`, `AI: Summary`, `AI: Score`, `AI: Criteria Breakdown`. Failures write `Analysis failed` or `Error: ...` into `AI: Summary` (and leave `AI: Score` empty, so a rerun retries them).
- Needs the sheet shared with the service account's `client_email`, and Drive links the service can download (public-by-link PDFs; DOCX links are not handled here).

`BACKEND_API_URL` is hardcoded near the top of `app.py`.

## Pipeline modules

### `jd_analyzer.py`
- `analyze_job_description(job_description, model)` -> dict with four top-level keys: `original_job_description`, `must_have_requirements` (technical_skills, experience, qualifications, core_responsibilities), `good_to_have_requirements` (additional_skills, extra_qualifications, bonus_experience), `additional_screening_criteria`. Returns `None` on any error (prints it).
- `format_requirements_for_display(requirements)` and `parse_edited_requirements(must_have_text, preferred_text, additional_text)` convert between that JSON and editable text.

### `resume_analyzer.py` - two separate scoring paths
1. **`analyze_resume(resume_text, requirements=None, model)`** (Tab 1, rich analysis).
   - **With requirements**: boolean match for every requirement item, then a qualitative assessment (project gravity, ownership/initiative, transferability), then a Yes/No recommendation. Returns `{"score": "X/Y", "analysis": {requirement_match, qualitative_assessment, final_recommendation, summary_of_key_factors, ...}}`.
   - **Without requirements**: JD-less summary (skills, key projects, education, qualitative assessment, career trajectory). Returns `{"score": "", "analysis": {resume_analysis, qualitative_assessment, summary_of_key_factors}}`.
   - `calculate_score(analysis)` counts `True` values across all boolean fields in `requirement_match` to build `"X/Y"`; with-JD branch only.
   - No retry logic; returns `None` on any exception.
2. **`analyze_resume_for_sheet(resume_text, job_description, model, api_key, criteria, jd_weight)`** (Tab 2 and the Render API; one flat JSON call).
   - Returns `{skills, strongest_language, summary, score (int 0-100), criteria_breakdown?}` or `None`.
   - **Score is computed in code, not by the model**, whenever `criteria` and/or `jd_weight` are used: the model returns a 0-100 sub-score per criterion (plus `overall_jd_fit_score` when `jd_weight > 0`) and the weighted average is computed here, so the arithmetic is auditable. With neither, the model's single holistic `score` is used.
   - Robust to model flakiness: up to 4 attempts, retrying on empty-but-valid JSON, missing `score`, `criteria_scores` length mismatch, missing `overall_jd_fit_score`, and rate limits (429/413 with 20s/40s/60s waits). Accepts common key aliases and list-vs-string skills.
   - `api_key` is optional (falls back per `get_client()`); `api.py` passes `OPENAI_API_KEY` explicitly.

The two score formats differ (`"X/Y"` string vs 0-100 int) and the two paths do not share prompts. Don't assume a change to one applies to the other.

## Working with the JSON schemas

Almost every bug or feature here comes down to the JSON contracts between files. When changing a prompt's output schema, trace every consumer:
- `jd_analyzer.format_requirements_for_display` / `parse_edited_requirements`
- `resume_analyzer.calculate_score`
- `app.py`: `flatten_analysis_for_csv`, the inline Tab 1 rendering (`qualitative_assessment.recruiter_style_summary`, `final_recommendation`, `contact_info`), the dormant `display_*` helpers, and the Tab 2 sheet-writing block
- `api.py` Pydantic models (`ResumeScoreResult`, `CriterionBreakdown`) for the sheet/API path

These assume specific nested keys and silently produce empty/`N/A` output (or KeyErrors) rather than erroring loudly if the schema drifts. For the sheet path, a changed key must also be handled in `analyze_resume_for_sheet`'s normalization (`pick(...)` aliases).

## Deployment

- **Render (backend)**: web service `BTA-Resume-Screener`, Python 3, free instance, auto-deploys from GitHub `main` (a push triggers a deploy in about 1.5 minutes). Needs env vars `OPENAI_API_KEY` and `BACKEND_API_KEY`. Render's dashboard holds the start command; the repo has no Render config file, so check there if it changes (expected: `uvicorn api:app --host 0.0.0.0 --port $PORT`). **Set or change env vars before pushing code that needs them.** After a deploy, `GET /health` should show `"openai_key_configured": true`.
- **Streamlit**: needs `[openai-key]`, `[backend-key]` and `[google_service_account]` secrets. Tab 2 depends on the Render service being up.
- `requirements.txt` is shared by both deployments (streamlit, openai, python-dotenv, PyPDF2, python-docx, pandas, plotly, streamlit-elements, gspread, oauth2client, requests, fastapi, uvicorn); versions are unpinned.

## Legacy files

- `google_sheet_resume_analyzer.py`: older standalone CLI duplicate of the Tab-2 workflow. Needs a local `service_account.json`, a hardcoded sheet URL, and stdin JD. It imports from `app.py` (running Streamlit page-config side effects) and uses the Tab-1 `analyze_resume` path and old column names. Not kept in sync with Tab 2; treat as legacy.
- `test_resume_analyzer.py`: manual smoke test with a hardcoded SDE JD and resume.
- `README.md` still describes the original OpenAI-key / model-picker setup and is out of date.

## Known gotchas

- Importing `google_sheet_resume_analyzer.py` or `app.py` executes Streamlit code at import time.
- Tab 2 skip logic keys on `AI: Score` being non-empty; a manually-typed value there makes the row skip.
- Scores from the old model (`gpt-oss-120b`) are not comparable with Luna's; recalibrate any cutoffs if mixing old and new sheet results.
- `/health` renamed its field to `openai_key_configured` (was `fireworks_key_configured`); update any monitor that checks the old name.
