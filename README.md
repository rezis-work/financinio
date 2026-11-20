# Financinio

AI-powered Personal Finance & Wealth platform built with **FastAPI**, **SvelteKit**, **Neon Serverless PostgreSQL**, **Upstash Vector**, **LangChain**, **LangGraph**, and **LangSmith**.

## Features Completed (Phases 1–5)

- **Phase 1 — Core Ledger & Auth**: Custom rotating JWT auth, multi-currency Accounts, searchable Transactions with linked internal transfers, default category seeding, and Cash Flow Dashboard.
- **Phase 2 — AI Document Ingestion**: LangGraph stateful pipeline (`CSV`, `Excel`, `PDF statements`, `Receipt images`) with balance reconciliation, fingerprint deduplication, 3-tier categorization (User Rules → Upstash Vector memory → LLM structured output), and HITL Review Queue (`interrupt()` / `Command(resume=...)`).
- **Phase 3 — Budgets, Recurring, Net Worth & Goals**: Rollover budgets with real-time month pacing, 50/30/20 setup, automatic recurring bill & subscription price-hike detector, Net Worth snapshots, Financial Goals, and deterministic **Snowball vs. Avalanche** & **What-If** simulators.
- **Phase 4 — Luna Multi-Agent AI Advisor**: LangGraph Supervisor routing across Ledger Analyst, Document & Memory RAG (Upstash Vector), Wealth Strategist, and HITL Action Agent (Approve/Reject database mutations in SSE streaming chat), plus Proactive Anomaly Detection & Weekly Digest.
- **Phase 5 — Evals, Hardening & Production Readiness**: Automated LangSmith & offline evaluation suite (`extraction`, `categorization`, `routing/math`, `PII redaction`), sliding-window rate limiting, security headers, Audit Logs, CSV/JSON full data export, GDPR-style account & vector namespace purge, Dark/Light theme toggle, `Dockerfile`, and `render.yaml`.

---

## Quick Start

### 1. Backend (FastAPI)

```bash
cd backend
cp .env.example .env
uv sync --python 3.12
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

API docs: `http://localhost:8000/docs`

### 2. Frontend (SvelteKit)

```bash
cd frontend
cp .env.example .env
pnpm install
pnpm dev --port 5173
```

Web app: `http://localhost:5173`

---

## Tests, Evals & Production Deployment

```bash
# Backend lint + integration tests (10 suites)
cd backend && uv run ruff check app tests && uv run pytest -v

# AI & Guardrail Evaluation Suite (offline or synced to LangSmith)
cd backend && uv run python -m app.ai.evals.run_evals
cd backend && uv run python -m app.ai.evals.run_evals --langsmith

# Frontend typecheck + production build
cd frontend && pnpm check && pnpm build
```

### Deployment
- **Backend**: Deploy `backend/Dockerfile` to Render (`render.yaml` included), Fly.io, or Railway with your Neon, Upstash Vector, OpenAI/Gemini, and LangSmith env vars.
- **Frontend**: Deploy `frontend/` to Vercel or Cloudflare Pages setting `PUBLIC_API_URL=https://your-api-domain/api/v1`.
