#!/bin/bash
# Start FastAPI server for Storywrangler backend

cd /users/j/s/jstonge1/storywrangler/backend
uv run fastapi run app/main.py --host 0.0.0.0 --port 3003
