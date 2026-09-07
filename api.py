"""
Standalone resume-screening backend API.

This is a separate deployment from the Streamlit app (app.py) - it exposes
the same "score a resume against a JD" logic over HTTP so other
applications can call it directly, without going through the Streamlit UI
or Google Sheets. Reuses resume_analyzer.analyze_resume_for_sheet, the
exact same function the Streamlit sheet flow calls, so both clients get
identical scoring behavior.

Run locally:
    uvicorn api:app --reload --port 8000

Deploy: a separate Render/Railway/Fly web service, NOT part of the
Streamlit Cloud deployment (Streamlit can't host arbitrary API routes -
see the conversation this was designed in for why).

Required environment variables (set as the platform's env vars/secrets,
not st.secrets - this process never touches Streamlit):
    FIREWORKS_API_KEY  - the same Fireworks key used by the Streamlit app
    BACKEND_API_KEY    - a separate shared secret callers must send back
                          as the X-API-Key header. Generate any long random
                          string for this; it is NOT the Fireworks key.
"""
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from resume_analyzer import analyze_resume_for_sheet

FIREWORKS_API_KEY = os.environ.get("FIREWORKS_API_KEY")
BACKEND_API_KEY = os.environ.get("BACKEND_API_KEY")
MAX_CONCURRENT_CALLS = 15
MAX_BATCH_SIZE = 100

app = FastAPI(
    title="Resume Screener API",
    description="Score resumes against a job description. Same logic as the BTA Resume Screener Streamlit app.",
    version="1.0.0",
)

# Open CORS - auth is via API key, not cookies/origin, so this is safe.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def check_auth(x_api_key: Optional[str]):
    if not BACKEND_API_KEY:
        # Misconfigured deployment - fail closed rather than accept anything.
        raise HTTPException(status_code=500, detail="Server misconfigured: BACKEND_API_KEY not set")
    if not x_api_key or x_api_key != BACKEND_API_KEY:
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key header")


class ResumeScoreRequest(BaseModel):
    job_description: str
    resume_text: str


class ResumeScoreResult(BaseModel):
    skills: str
    strongest_language: str
    summary: str
    score: int


class ResumeItem(BaseModel):
    id: str
    resume_text: str


class BatchScoreRequest(BaseModel):
    job_description: str
    resumes: List[ResumeItem] = Field(..., max_length=MAX_BATCH_SIZE)


class BatchScoreResultItem(BaseModel):
    id: str
    result: Optional[ResumeScoreResult] = None
    error: Optional[str] = None


class BatchScoreResponse(BaseModel):
    results: List[BatchScoreResultItem]


@app.get("/health")
def health():
    """Unauthenticated liveness check - does not verify the Fireworks key works."""
    return {"status": "ok", "fireworks_key_configured": bool(FIREWORKS_API_KEY)}


@app.post("/score-resume", response_model=ResumeScoreResult)
def score_resume(payload: ResumeScoreRequest, x_api_key: Optional[str] = Header(None)):
    """Score a single resume against a job description."""
    check_auth(x_api_key)
    result = analyze_resume_for_sheet(payload.resume_text, payload.job_description, api_key=FIREWORKS_API_KEY)
    if result is None:
        raise HTTPException(status_code=502, detail="Resume analysis failed (upstream LLM error)")
    return result


@app.post("/score-resumes", response_model=BatchScoreResponse)
def score_resumes(payload: BatchScoreRequest, x_api_key: Optional[str] = Header(None)):
    """
    Score up to 100 resumes against one job description in a single request.
    Each resume still requires its own LLM call under the hood - these run
    concurrently (bounded by MAX_CONCURRENT_CALLS) rather than sequentially,
    so 100 resumes take roughly total_resumes / MAX_CONCURRENT_CALLS call-durations,
    not 100 call-durations. One resume's failure does not fail the batch -
    it comes back as an item with `error` set instead of `result`.
    """
    check_auth(x_api_key)

    def _score_one(item: ResumeItem) -> BatchScoreResultItem:
        try:
            result = analyze_resume_for_sheet(item.resume_text, payload.job_description, api_key=FIREWORKS_API_KEY)
            if result is None:
                return BatchScoreResultItem(id=item.id, error="Resume analysis failed (upstream LLM error)")
            return BatchScoreResultItem(id=item.id, result=ResumeScoreResult(**result))
        except Exception as e:
            return BatchScoreResultItem(id=item.id, error=str(e))

    results: List[Optional[BatchScoreResultItem]] = [None] * len(payload.resumes)
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_CALLS) as executor:
        future_to_idx = {executor.submit(_score_one, item): i for i, item in enumerate(payload.resumes)}
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            results[idx] = future.result()

    return BatchScoreResponse(results=results)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
