# Douyin Auto API

FastAPI backend for the Douyin Android automation admin system.

## Quick Start

```bash
cd api
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

API prefix is `/api`.

Health check:

```bash
curl http://127.0.0.1:8000/api/health
```
