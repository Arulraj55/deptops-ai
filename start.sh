#!/usr/bin/env bash
set -euo pipefail

# Start FastAPI (uvicorn) bound to localhost:8000 in background,
# then start Streamlit on the Render-provided $PORT in foreground.

# If PORT not set, default to 8000 for Streamlit (useful locally)
: ${PORT:=8000}

echo "Starting FastAPI on 127.0.0.1:8000"
uvicorn api:app --host 127.0.0.1 --port 8000 &
UVICORN_PID=$!

echo "Starting Streamlit on 0.0.0.0:${PORT}"
streamlit run app.py --server.port ${PORT} --server.address 0.0.0.0

# When Streamlit exits, ensure uvicorn is killed
kill ${UVICORN_PID} || true
