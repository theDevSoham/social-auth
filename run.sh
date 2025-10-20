#!/bin/sh

# Run FastAPI with Uvicorn using uv
uv run uvicorn main:app --reload --host 0.0.0.0 --port 6217
