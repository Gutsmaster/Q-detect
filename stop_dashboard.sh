#!/usr/bin/env bash
# Stop the dashboard started by run_dashboard.sh / python dashboard/app.py
PORT="${QDETECT_PORT:-5055}"
cd "$(dirname "$0")"

if command -v lsof >/dev/null 2>&1; then
  PIDS=$(lsof -t -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)
  if [ -n "$PIDS" ]; then
    kill $PIDS
    echo "Stopped dashboard on port $PORT."
  else
    echo "Nothing is listening on port $PORT."
  fi
else
  echo "Could not find lsof. In the terminal that started the dashboard, press Ctrl+C."
fi
