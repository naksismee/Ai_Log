# AI Log Analyzer

A Python/FastAPI dashboard that groups repeated error and warning messages into issue clusters, summaries, remembered issues, and searchable analysis history.

## Quick start

Install **Python 3.10 or later** (3.12 recommended) and Git, then run:

```sh
git clone https://github.com/naksismee/Ai_Log.git
cd Ai_Log
python3 run.py --demo
```

On Windows, use `py run.py --demo` if `python3` is unavailable.

Open **http://127.0.0.1:8000** and click **Try sample log**. The launcher creates an isolated environment and installs the small demo dependency set on the first run. No shell activation, API key, or ML model download is needed. Later launches reuse the environment.

Stop with **Ctrl+C**. If the port is busy, use `python3 run.py --demo --port 8001`.

### Walkthrough

1. Click **Try sample log** to analyse bundled synthetic errors.
2. Inspect issue groups, occurrence counts, summaries, and explanations.
3. Analyse the sample again to see matches against remembered issues.
4. Search for `database connection refused` in the search panel.
5. Open an entry in **Recent runs** to revisit its results.
6. Upload a `.log` or `.txt` file to try your own input.

The sample has **33 issue lines** in three repeated groups. At the default threshold, demo mode produces counts of **24**, **6**, and **3**, with frequency-based HIGH, MEDIUM, and LOW severity.

**Demo mode uses deterministic keyword vectors.** It demonstrates the workflow without transformer-level semantic matching. Explanations use local rules; the demo launcher disables external LLM calls and Slack alerts.

## Run the semantic version

```sh
python3 run.py
```

This installs `backend/requirements.txt` and uses Sentence Transformers (`all-MiniLM-L6-v2`). The first analysis downloads the model from Hugging Face and may take longer. A paid API key is not required for clustering, matching, vector search, or local explanations.

For manual setup:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
cd backend
ENABLE_SCHEDULER=false python -m uvicorn app.main:app --reload
```

Windows activation: `.venv\Scripts\activate`. The dashboard and API are served by the same FastAPI application; no separate frontend build is needed.

## Features

- Parses common formats and selects ERROR/WARNING lines.
- Groups messages using normalized embeddings and cosine similarity.
- Assigns severity by frequency: 20+ HIGH, 5–19 MEDIUM, fewer than 5 LOW.
- Generates summaries and local possible-cause explanations.
- Remembers issue representatives in SQLite for later matching.
- Saves uploaded analyses to a browsable history.
- Searches representatives using ChromaDB when available, with an in-memory fallback.
- Produces hourly trend buckets from original timestamped lines.
- Supports optional monitoring, Slack alerts, and LLM explanations.

Clustering is greedy: each message is compared with existing representatives. Higher thresholds usually create more, tighter groups. Results help investigation; they do not prove a root cause.

## API

Interactive API documentation: **http://127.0.0.1:8000/docs**.

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Readiness and active analysis mode |
| `GET /sample-log` | Synthetic walkthrough log |
| `POST /analyze-log` | Upload and persist an analysis |
| `GET /recent-runs` | List saved analyses |
| `GET /runs/{id}` | Retrieve a saved analysis |
| `GET /semantic-search?q=...` | Search cluster representatives |
| `GET /known-issues` | Inspect remembered issues |
| `DELETE /known-issues` | Clear remembered issues |
| `POST /analyze-path` | Analyse a file in the configured watch directory |

From the repository root, with the server running:

```sh
curl -F "file=@sample_logs/recruiter.log" \
  "http://127.0.0.1:8000/analyze-log?threshold=0.80&alert=false"
```

## Data and optional integrations

The launcher saves runtime data under `data/demo` or `data/semantic`. These paths are excluded from Git. No personal log upload is required to review the project.

| Environment variable | Purpose |
| --- | --- |
| `AI_LOG_ANALYZER_DATA_DIR` | SQLite/vector storage directory |
| `AI_LOG_ANALYZER_DEMO` | Enable keyword-vector preview mode |
| `ENABLE_SCHEDULER` | Periodic analysis; launcher defaults to `false` |
| `LOG_WATCH_DIR` | Directory containing monitored `.log` files |
| `ANALYZE_INTERVAL_SECONDS` | Monitoring interval; minimum 10 seconds |
| `SLACK_WEBHOOK_URL` | Optional HIGH-severity alerts |
| `OPENAI_API_KEY` | Optional external LLM explanations |
| `OPENAI_MODEL` | Optional explanation model |
| `OPENAI_BASE_URL` | Optional compatible API endpoint |

Configure integrations when starting the semantic backend directly; the demo launcher disables external calls. Review logs before enabling external explanations or alerts.

## Tests

```sh
python3 -m venv .venv-test
source .venv-test/bin/activate
python -m pip install -r backend/requirements-demo.txt httpx
python -m unittest discover -s tests -v
```

Checks use temporary data and cover sample analysis, saved history, repeated-issue matching, search, validation, and timestamp trends. They do not download model weights or call external AI services.

## Project structure

```text
run.py                    Cross-platform launcher
backend/app/main.py       API endpoints
backend/app/parser.py     Log parsing
backend/app/cluster.py    Embedding-based grouping
backend/app/embedder.py   Semantic model and lightweight demo vectors
backend/app/memory.py     Remembered issues
backend/app/storage.py    Analysis history
backend/app/static/       Dashboard HTML, CSS, and JavaScript
sample_logs/              Synthetic walkthrough inputs
tests/                    Offline integration checks
```

## Troubleshooting

- **No module named app:** use the root launcher, or change into `backend` before running Uvicorn manually.
- **Slow model download:** use `--demo` for a preview without model weights.
- **Package installation fails on a newer Python:** try Python 3.12 in a fresh environment.
- **Search is empty:** analyse a log first. In-memory search is reset when the process restarts.
- **Database permission error:** select a writable data directory when starting manually.
