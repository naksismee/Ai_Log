# Creating virtual environment
python3 -m venv venv
source venv/bin/activate

# If using Conda, deactivate base:
conda deactivate

# Install Dependencies
pip install -r requirements.txt
# If needed manually:
pip install fastapi uvicorn sentence-transformers numpy python-multipart

# Running the Application
uvicorn app.main:app --reload

http://127.0.0.1:8000

## API endpoints

- `GET /health`
- `GET /` (Dashboard UI)
- `POST /analyze-log` (multipart upload)
  - Query params: `threshold` (0..1), `model_name`, `remember` (store known issues), `alert` (Slack webhook)
  - Returns: clustered issues + summaries + best-match known issue (if any) + `ai_explanation`
- `POST /analyze-path` (analyze server-side file from `LOG_WATCH_DIR` by relative path)
- `GET /recent-runs` (list recent persisted analysis runs)
- `GET /runs/{run_id}` (run details + clusters)
- `GET /semantic-search` (semantic search over stored cluster representatives)
- `GET /known-issues` (lists remembered issue representatives)
- `DELETE /known-issues` (clears remembered issues)

## Optional: Slack alerts

Set `SLACK_WEBHOOK_URL` to enable alerts for HIGH-severity clusters.

## Optional: LLM explanations

If you set `OPENAI_API_KEY`, the backend will generate richer per-cluster explanations using an OpenAI-compatible API.

- `OPENAI_API_KEY`
- `OPENAI_MODEL` (default: `gpt-4o-mini`)
- `OPENAI_BASE_URL` (default: `https://api.openai.com/v1`)

## Optional: Scheduled monitoring

The backend can periodically analyze the newest `*.log` in `LOG_WATCH_DIR` and persist results.

- `ENABLE_SCHEDULER` (default: `true`)
- `LOG_WATCH_DIR` (default: `../sample_logs`)
- `ANALYZE_INTERVAL_SECONDS` (default: `60`, minimum: `10`)
- `EMBED_MODEL_NAME` (default: `all-MiniLM-L6-v2`)
- `CLUSTER_THRESHOLD` (default: `0.80`)
- `REMEMBER_KNOWN_ISSUES` (default: `true`)
- `ENABLE_ALERTS` (default: `true`)

## Vector database

This project uses **ChromaDB** for persistent vector search when installed (`chromadb`).
If Chroma can’t load, the app falls back to an in-memory vector store (semantic search will only cover the current process).
