# Model choice: gpt-oss-120b vs GPT-6 Luna

**Decision (2026-10-30): use `gpt-6-luna` at `medium` reasoning effort, via OpenAI.**
Configured in `llm_config.py` (`LLM_MODEL`, `REASONING_EFFORT`). Previously the app
used `accounts/fireworks/models/gpt-oss-120b` at medium effort via Fireworks AI.

## Why

1. **gpt-oss-120b was unstable.** The same resume scored 55 at medium and 73 at high
   effort. Luna stayed within 4 points across medium/high/xhigh on every resume.
   The pipeline ranks candidates, so score stability matters most.
2. **Cheaper.** About $0.0005 per resume on Luna medium vs $0.0012 on gpt-oss-120b
   medium (about 60% less), mostly because Luna used about a third of the reasoning tokens.
3. **More reliable.** 0 retries in 9 Luna calls. gpt-oss-120b medium returned an empty
   `criteria_scores` once and needed a retry (the failure class behind the existing
   "model omitted score" / length-mismatch retry logic in `resume_analyzer.py`).
4. **Higher effort did not pay.** Luna high/xhigh moved scores by a few points at
   about 20% / 60% more cost, and xhigh roughly doubled latency.

## Test setup

- 3 resumes picked at random from a local Downloads folder (two are versions of the
  same person's resume, so this is a small sample).
- The SDE job description from `test_resume_analyzer.py`, with 3 weighted criteria and
  `jd_weight=30`, through `analyze_resume_for_sheet` (the path the Render backend and
  the Streamlit sheet flow use).
- One run per resume per configuration, 15 calls in total, `max_completion_tokens=4096`.
- Costs computed from the API's reported token usage and aggregator-listed prices:
  gpt-oss-120b on Fireworks $0.15 in / $0.60 out per 1M tokens; Luna $0.10 / $0.50.
  These were not checked against invoices.

## Results

Scores (0-100):

| Resume | oss-120b medium | oss-120b high | Luna medium | Luna high | Luna xhigh |
|---|---|---|---|---|---|
| Resume A | 55 | 73 | 73 | 70 | 74 |
| Resume B | 50 | 49 | 70 | 68 | 70 |
| Resume C | 57 | 49 | 44 | 46 | 42 |

Average per resume:

| Config | Cost | Latency | Reasoning tokens | Retries |
|---|---|---|---|---|
| oss-120b medium (previous) | $0.0012 | ~7s | ~900 | 1 in 3 |
| oss-120b high | $0.0022 | ~16s | ~2,800 | 0 |
| **Luna medium (chosen)** | **$0.0005** | ~7s | ~280 | 0 |
| Luna high | $0.0006 | ~9s | ~490 | 0 |
| Luna xhigh | $0.0007 | ~14s | ~805 | 0 |

No call hit the 4096-token output cap.

gpt-oss-120b has no `xhigh` setting (low/medium/high only).

## Caveats

- **Scores are not comparable to the old model's.** Luna scored the "2-5 years
  experience" criterion 85-88 where gpt-oss-120b medium gave 40-45 for a candidate with
  about 2 years 9 months. Luna looks more accurate there, but recalibrate any score
  cutoffs used downstream.
- **No ground truth.** This shows Luna agrees with itself more and costs less, not that
  its ranking is better. Spot-check against candidates you have already judged.
- **Published benchmarks were third-party and inconsistent.** Artificial Analysis
  Intelligence Index figures for both models varied by page and index version, so they
  were not used for the decision.
- **Closed model.** Luna can't be pinned or self-hosted; a provider-side update could
  shift scores.

## Code changes made with the switch

- New `llm_config.py`: single source for model, effort and client (`get_client()`).
- `jd_analyzer.py`: removed `temperature=0.19` (not set for reasoning models) and replaced
  `max_tokens=1147` with `max_completion_tokens=4096`, since reasoning tokens count
  against the cap.
- `api.py`: reads `OPENAI_API_KEY` instead of `FIREWORKS_API_KEY`; `/health` now returns
  `openai_key_configured` instead of `fireworks_key_configured`.
- `app.py`: sidebar shows the OpenAI model; the delay-field help text no longer
  describes Fireworks limits.

## Deployment checklist

- Streamlit Cloud: add `[openai-key]` / `OPENAI_API_KEY` under app Secrets.
- Render (`bta-resume-screener.onrender.com`): set the `OPENAI_API_KEY` env var, then
  redeploy. Until then, Streamlit Tab 2 and API callers will fail.
- `FIREWORKS_API_KEY` / `[fireworks-key]` / `[groq-key]` are no longer used and can be removed.

## Re-running the comparison

To compare another model or effort, set `LLM_MODEL` / `REASONING_EFFORT` in
`llm_config.py`, run the same JD and resumes through `analyze_resume_for_sheet`, and
record the score, tokens (`usage.completion_tokens_details.reasoning_tokens`), latency
and retry count per call.
