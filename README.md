# Financinio

AI-powered Personal Finance & Wealth platform built with **FastAPI**, **SvelteKit**, **Neon Serverless PostgreSQL**, **Upstash Vector**, **LangChain**, **LangGraph**, and **LangSmith**.

## Architecture

- **`backend/`**: FastAPI + async SQLAlchemy 2.0 + Alembic + custom rotating JWT auth + pluggable file storage (`local` or S3/Cloudflare R2) + LangChain provider-agnostic LLM factory + LangGraph stateful document ingestion pipeline (with Human-in-the-Loop `interrupt()` review & Neon Postgres checkpointing) + Upstash Vector per-user namespaces (`merchant_memory:{user_id}` and `documents:{user_id}`) + LangSmith tracing.
- **`frontend/`**: SvelteKit (Svelte 5 + TypeScript + Tailwind CSS v4) with Dashboard, Accounts, Searchable Ledger, Drag-and-Drop AI Statement/Receipt Imports + HITL Review Queue, and Settings/Rules.

---

## Quick Start

### 1. Backend (FastAPI)

```bash
cd backend
cp .env.example .env
# Edit .env with your Neon DATABASE_URL, Upstash Vector, LLM key, and LangSmith key (optional for local SQLite dev)
uv sync --python 3.12
```

Run migrations (when using Neon PostgreSQL):

```bash
uv run alembic upgrade head
```

Start the FastAPI server:

```bash
uv run uvicorn app.main:app --reload --port 8000
```

API docs will be available at `http://localhost:8000/docs`.

### 2. Frontend (SvelteKit)

```bash
cd frontend
cp .env.example .env
pnpm install
pnpm dev
```

Open `http://localhost:5173`.

---

## Running Tests & Checks

```bash
# Backend pytest suite (Auth, Ledger, Transfers, Dashboard, LangGraph HITL Ingestion + Vector Learning)
cd backend && uv run pytest -v

# Frontend TypeScript & Svelte checks + production build
cd frontend && pnpm check && pnpm build
```
