# 🔍 BreakMyApp

> **Autonomous Software Reliability Platform** — Scan any GitHub repository for secrets, security vulnerabilities, code quality issues, and dependency risks in seconds.

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat&logo=fastapi)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-14-black?style=flat&logo=nextdotjs)](https://nextjs.org)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat&logo=python)](https://python.org)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat&logo=docker)](https://docs.docker.com/compose/)

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Local Development with Docker](#local-development-with-docker)
  - [Manual Setup](#manual-setup)
- [Environment Variables](#environment-variables)
- [API Reference](#api-reference)
- [GitHub Actions Integration](#github-actions-integration)
- [Webhook Support](#webhook-support)
- [Scoring System](#scoring-system)
- [Deployment](#deployment)

---

## Overview

**BreakMyApp** is a full-stack platform that performs automated, multi-scanner security and reliability analysis on GitHub repositories. Submit a repo URL via API or the web UI — the platform clones it, runs four parallel scanner passes, generates an AI-powered explanation via the Gemini API, scores it out of 100, and delivers a structured report.

Results can be consumed via:
- The **web dashboard** (Next.js frontend)
- The **REST API** directly
- A **GitHub Actions** workflow that posts findings as PR comments and issues
- A **webhook callback URL** for async integrations

---

## Architecture

```
+---------------------------------------------------------+
|                      Frontend (Next.js)                  |
|                  Firebase Auth · Tailwind CSS            |
+------------------------+--------------------------------+
                         | HTTP
+------------------------v--------------------------------+
|               Backend API (FastAPI · Python 3.11)        |
|  /api/v1/scans   /api/v1/github   /api/v1/auth          |
+-------+-----------------------------------+-------------+
        | Enqueue Task                      | Store Results
+-------v------------------+       +--------v------------+
|  Celery Worker           |       |    PostgreSQL        |
|  (Redis Broker)          |       |    (via SQLAlchemy)  |
+-------+------------------+       +---------------------+
        | Runs
+-------v--------------------------------------------------------+
|                   Scanner Pipeline                              |
|                                                                 |
|  TruffleHog (Secrets) · Semgrep (Security)                     |
|  Bandit (Python Code Quality) · pip-audit (Deps)               |
|                                                                 |
|  -> Gemini AI Explanation & Prioritization                      |
|  -> MinIO Artifact Storage                                      |
|  -> Webhook Delivery (optional)                                 |
+----------------------------------------------------------------+
```

---

## Features

| Feature | Description |
|---|---|
| 🔐 **Secrets Detection** | TruffleHog scans for leaked API keys, tokens, and credentials |
| 🛡️ **SAST Security** | Semgrep static analysis for common vulnerability patterns |
| 🐍 **Code Quality** | Bandit analysis for Python-specific security anti-patterns |
| 📦 **Dependency Audit** | pip-audit checks for known CVEs in Python dependencies |
| 🤖 **AI Explanation** | Gemini Pro generates plain-English findings summaries and prioritized action items |
| 📊 **Scoring** | 0–100 production readiness score with severity-weighted deductions |
| 🔔 **Webhooks** | Optional callback URL POSTed to when scan completes |
| 🐙 **GitHub Integration** | Post scan results as PR comments and create GitHub Issues for critical findings |
| 🗄️ **Artifact Storage** | Raw scanner JSON outputs stored in MinIO (S3-compatible) |
| 🔑 **Auth** | Firebase Authentication with optional anonymous scan support |
| ⚡ **Rate Limiting** | Per-IP rate limiting on scan submission endpoint |

---

## Tech Stack

### Backend
| Layer | Technology |
|---|---|
| API Framework | FastAPI 0.115 |
| Language | Python 3.11 |
| ORM | SQLAlchemy 2.0 (async) |
| Database | PostgreSQL 15 |
| Task Queue | Celery 5.4 + Redis 7 |
| Object Storage | MinIO (S3-compatible) |
| AI | Google Gemini API (`google-generativeai`) |
| Auth | Firebase Admin SDK |
| Scanners | TruffleHog, Semgrep 1.100, Bandit, pip-audit |

### Frontend
| Layer | Technology |
|---|---|
| Framework | Next.js 14 |
| Language | TypeScript |
| Styling | Tailwind CSS |
| Auth | Firebase Auth (client SDK) |

### Infrastructure
| Component | Technology |
|---|---|
| Containerization | Docker + Docker Compose |
| Deployment | Railway |
| CI Integration | GitHub Actions |

---

## Project Structure

```
BreakMyApp/
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py                  # FastAPI app entrypoint & CORS config
│       ├── celery_app.py            # Celery configuration
│       ├── core/
│       │   ├── config.py            # Pydantic settings (env vars)
│       │   ├── database.py          # Async SQLAlchemy engine & session
│       │   ├── auth.py              # Firebase auth dependency
│       │   └── limiter.py           # Per-IP rate limiter
│       ├── models/
│       │   ├── scan.py              # Scan SQLAlchemy model
│       │   └── user.py              # User SQLAlchemy model
│       ├── schemas/
│       │   └── scan.py              # Pydantic request/response schemas
│       ├── api/v1/routes/
│       │   ├── scans.py             # Scan CRUD + artifact endpoints
│       │   ├── github.py            # GitHub PR comment / issue reporter
│       │   └── auth.py              # Auth routes
│       ├── services/
│       │   ├── repo_handler.py      # Git clone & cleanup utilities
│       │   ├── ai_explainer.py      # Gemini AI integration
│       │   ├── github_reporter.py   # GitHub API integration
│       │   ├── minio_service.py     # MinIO upload & presigned URL generation
│       │   ├── webhook_service.py   # Webhook delivery with retry logic
│       │   └── scanners/
│       │       ├── secrets_scanner.py     # TruffleHog wrapper
│       │       ├── semgrep_scanner.py     # Semgrep wrapper
│       │       ├── bandit_scanner.py      # Bandit wrapper
│       │       └── dependency_scanner.py  # pip-audit wrapper
│       └── tasks/
│           └── analysis.py          # Celery task: full scan pipeline
├── frontend/
│   ├── Dockerfile
│   ├── app/                         # Next.js App Router pages
│   ├── components/                  # React components
│   └── lib/                         # Firebase client, API utilities
├── github-action-template/
│   └── breakmyapp.yml               # Drop-in GitHub Actions workflow
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Getting Started

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (recommended)
- Or: Python 3.11, Node.js 18+, PostgreSQL 15, Redis 7

### Local Development with Docker

**1. Clone the repository**
```bash
git clone https://github.com/your-org/breakmyapp.git
cd breakmyapp
```

**2. Configure environment variables**
```bash
cp .env.example .env
# Edit .env with your values (see Environment Variables section below)
```

**3. Add your Firebase service account**

Download your Firebase service account JSON from the [Firebase Console](https://console.firebase.google.com/) and place it at:
```
backend/firebase-service-account.json
```

**4. Start all services**
```bash
docker compose up --build
```

This starts:
- `breakmyapp-postgres` on port `5432`
- `breakmyapp-redis` on port `6379`
- `breakmyapp-minio` on ports `9000` (API) and `9001` (Console)
- `breakmyapp-backend` (FastAPI) on port `8000`
- `breakmyapp-worker` (Celery)

**5. Verify the API is running**
```bash
curl http://localhost:8000/health
# -> {"status": "ok"}
```

**6. Access MinIO Console**

Open [http://localhost:9001](http://localhost:9001) and log in with `minioadmin` / `minioadmin`.

### Manual Setup

#### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
pip install semgrep==1.100.0 bandit

# Run migrations
alembic upgrade head

# Start API server
uvicorn app.main:app --reload --port 8000

# Start Celery worker (separate terminal)
celery -A app.celery_app worker --loglevel=info
```

#### Frontend
```bash
cd frontend
npm install
npm run dev
# -> http://localhost:3000
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in the values:

```env
# PostgreSQL — async DSN
DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/breakmyapp

# Redis — Celery broker & result backend
REDIS_URL=redis://redis:6379/0

# MinIO — S3-compatible object storage
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin

# Google Gemini API key
GEMINI_API_KEY=your_gemini_api_key_here

# Application environment
ENVIRONMENT=development
```

> **Note:** `FIREBASE_SERVICE_ACCOUNT_JSON_FILE` is set automatically by Docker Compose and points to `backend/firebase-service-account.json`. Do **not** commit this file — it is listed in `.gitignore`.

---

## API Reference

Base URL (production): `https://breakmyapp-production-2f29.up.railway.app`
Base URL (local): `http://localhost:8000`

### Health Check

```
GET /health
-> {"status": "ok"}
```

### Submit a Scan

```
POST /api/v1/scans/
Content-Type: application/json

{
  "repo_url": "https://github.com/owner/repo",
  "callback_url": "https://your-server.com/webhook"
}
```

`callback_url` is optional. `repo_url` must be a valid `https://github.com/` URL.

**Response `201 Created`:**
```json
{
  "id": "uuid",
  "repo_url": "https://github.com/owner/repo",
  "callback_url": "https://your-server.com/webhook",
  "status": "pending",
  "score": null,
  "findings": null,
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z"
}
```

### Get Scan

```
GET /api/v1/scans/{scan_id}
```

### Get Scan Summary

```
GET /api/v1/scans/{scan_id}/summary
```

**Response (completed scan):**
```json
{
  "status": "completed",
  "score": 72,
  "repo_url": "https://github.com/owner/repo",
  "report_url": "https://breakmyapp-production-2f29.up.railway.app/scan/{scan_id}",
  "findings_summary": {
    "secrets": 0,
    "security": 3,
    "code_quality": 5,
    "dependencies": 2
  },
  "top_priorities": ["Fix SQL injection in views.py", "..."],
  "executive_summary": "The repository has several medium-severity issues..."
}
```

### Get Artifact Download URLs

```
GET /api/v1/scans/{scan_id}/artifacts
```

Returns presigned MinIO URLs (valid 1 hour) for the raw scanner JSON outputs:
`secrets.json`, `semgrep.json`, `bandit.json`, `dependencies.json`

### List My Scans (requires auth)

```
GET /api/v1/scans/?limit=20
Authorization: Bearer <firebase-id-token>
```

### Post GitHub Report

```
POST /api/v1/github/report/{scan_id}
Content-Type: application/json

{
  "token": "github_pat_...",
  "owner": "repo-owner",
  "repo": "repo-name",
  "pr_number": 42
}
```

---

## GitHub Actions Integration

Add automated security scanning to any repository's PR workflow using the provided template.

**1. Copy the workflow file to your target repository:**
```bash
cp github-action-template/breakmyapp.yml .github/workflows/breakmyapp.yml
```

**2. Add the `BREAKMYAPP_TOKEN` secret** in your repository
(Settings → Secrets and variables → Actions → New repository secret)

Use a GitHub Personal Access Token with `repo` and `issues:write` scopes.

**3. Open a pull request** — the workflow will automatically:
1. Submit a scan for the PR's repository URL
2. Poll until the scan completes (timeout: 20 minutes)
3. Post a formatted comment on the PR with score and findings summary
4. Create GitHub Issues for critical findings
5. Print the final score and report link to the Actions log

---

## Webhook Support

When submitting a scan, you can optionally include a `callback_url`. Once the scan completes (or fails), BreakMyApp will `POST` the following payload to that URL:

```json
{
  "event": "scan.completed",
  "scan_id": "uuid",
  "repo_url": "https://github.com/owner/repo",
  "status": "completed",
  "score": 72,
  "report_url": "https://breakmyapp-production-2f29.up.railway.app/scan/uuid",
  "findings_summary": {
    "secrets": 0,
    "security": 3,
    "code_quality": 5,
    "dependencies": 2
  },
  "top_priorities": ["Fix SQL injection in views.py", "..."],
  "executive_summary": "The repository has several medium-severity issues...",
  "timestamp": "2026-01-01T00:00:00Z"
}
```

**Delivery behavior:**
- Up to **3 attempts**, with a **2-second delay** between retries
- **10-second timeout** per attempt
- `callback_url` must begin with `http://` or `https://`
- Delivery failures are logged but never block the scan result

---

## Scoring System

Scans start at **100** and deductions are applied per finding based on severity across all four scanners:

| Severity | Secrets | Security (Semgrep) | Code Quality (Bandit) | Dependencies |
|---|---|---|---|---|
| CRITICAL | -20 | — | — | -20 |
| HIGH | -10 | -10 | -10 | -10 |
| MEDIUM | -5 | -5 | -5 | -5 |
| LOW | — | -2 | -2 | -2 |

Score is floored at `0`. A score of **100** means no findings across all scanners.

| Score | Status |
|---|---|
| 80–100 | ✅ Production ready |
| 60–79 | ⚠️ Minor issues |
| 40–59 | 🟠 Significant issues |
| 0–39 | ❌ Critical — not production ready |

---

## Deployment

The project is deployed on **Railway**:

- **Backend API** — Python 3.11 Docker container (FastAPI + Uvicorn)
- **Celery Worker** — Same Docker image, different start command
- **Frontend** — Node.js Docker container (Next.js)
- **PostgreSQL 15** — Railway managed database plugin
- **Redis 7** — Railway managed Redis plugin

Environment variables are configured per-service in the Railway dashboard. The MinIO service in production is an external S3-compatible provider with TLS enabled (`secure=True`).

> **Note for local development:** The default Docker Compose setup runs MinIO without TLS. If you encounter connection errors when switching between environments, verify that `secure=True/False` in `backend/app/services/minio_service.py` matches your MinIO provider's configuration.

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit your changes: `git commit -m 'Add my feature'`
4. Push to the branch: `git push origin feature/my-feature`
5. Open a Pull Request — the BreakMyApp GitHub Action will automatically scan your changes!

---

## License

This project is proprietary software. All rights reserved.
