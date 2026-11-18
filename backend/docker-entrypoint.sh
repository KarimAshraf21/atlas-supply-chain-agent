#!/bin/sh
set -e
# Load the knowledge graph on first start (or when ATLAS_RELOAD=1), then serve.
if [ "${ATLAS_RELOAD:-0}" = "1" ] || ! python -c "from atlas.graph import run; import sys; sys.exit(0 if run('MATCH (n) RETURN count(n) AS n')[0]['n'] > 0 else 1)"; then
  echo "Loading knowledge graph…"
  atlas load
  atlas reason
fi
exec uvicorn atlas.api.app:app --host 0.0.0.0 --port 8000
