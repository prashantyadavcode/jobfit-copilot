# JobFit Copilot

Interview-ready NLP project that analyzes resume-job fit using skills extraction, entity recognition, keyword overlap, and semantic term similarity.

## Features
- Upload resume (PDF/DOCX/TXT) + paste JD
- Skill extraction using spaCy + curated NLP/ML skill dictionary
- Match score calculation (skill overlap + fuzzy semantic similarity)
- Missing skills and actionable resume rewrite suggestions
- LaTeX resume section extraction and targeted rewrite flow using local Ollama (free)
- FastAPI backend + built-in frontend at `/`

## UI Walkthrough

### Step 1 — Analyze Match
Upload your resume and paste the job description, then run the match analysis.

![Step 1 — Analyze Match](ui-steps/Step%201%20-%20Analyze%20Match.png)

### Step 2 — Match Results
Review your fit score, matched skills, gaps, and improvement suggestions.

![Step 2 — Match Results](ui-steps/Step%202%20-%20Match%20Results.png)

### Step 3 — Add LaTeX Resume Code
Paste your LaTeX source and select the sections you want to improve.

![Step 3 — Adding LaTeX Code](ui-steps/Step%203%20-%20Adding%20LatexCode.png)

### Step 4 — Improved LaTeX Output
Rewrite selected sections and download the updated `.tex` file.

![Step 4 — Improved LaTeX Code](ui-steps/Step%204%20-%20Improved%20LatexCode.png)

## Run
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
# Optional for real PDF preview (Overleaf-like): install a LaTeX compiler
# brew install --cask mactex-no-gui
# Optional one-time local model setup:
# brew install ollama
# ollama serve
# ollama pull llama3.2:3b
uvicorn app.main:app --reload --port 8000
```

Open: http://localhost:8000/

## Deploy to Vercel

This project is configured for [Vercel's FastAPI preset](https://vercel.com/docs/frameworks/backend/fastapi). The API entrypoint is `app.main:app` (see `pyproject.toml`).

### One-time setup

1. Push the repo to GitHub and [import it in Vercel](https://vercel.com/new).
2. Vercel auto-detects Python from `requirements.txt` and runs the build script in `pyproject.toml` to verify the spaCy model.
3. Add these **Environment Variables** in the Vercel project settings:

| Variable | Value |
|----------|-------|
| `LLM_PROVIDER` | `openai` |
| `OPENAI_API_KEY` | your OpenAI API key |
| `OPENAI_MODEL` | `gpt-4.1-mini` (or another supported model) |
| `APP_ENV` | `production` |

> **Note:** Ollama and local LaTeX compilers (`pdflatex`) are not available on Vercel. Resume analysis works out of the box; LaTeX section rewrites require OpenAI (or another remote LLM you configure).

Static assets are served from `public/` via the Vercel CDN. API routes are handled by the FastAPI serverless function.

### Deploy with CLI

```bash
npm i -g vercel   # or: brew install vercel-cli
vercel login
vercel            # preview deploy
vercel --prod     # production deploy
```

Local preview with the Vercel runtime:

```bash
pip install -r requirements-dev.txt
vercel dev
```

## API
- `POST /analyze/text` -> analyze plain text resume + JD
- `POST /analyze/files` -> analyze uploaded resume + JD file
- `POST /analyze/mixed` -> analyze uploaded resume + pasted JD

## Why this stands out for NLP roles
- End-to-end NLP pipeline
- Production API design with file ingestion
- Practical model outputs with explainable matching
- Deployment-ready structure

## Tech Stack & Skills

**Languages** — Python, JavaScript, HTML, CSS, LaTeX

**Backend & API** — FastAPI, Uvicorn, Pydantic, REST API, Multipart uploads, httpx

**NLP & Text Processing** — spaCy, NER, Skill extraction, Lemmatization, RapidFuzz, Regex

**LLM & AI** — Ollama (Llama 3.2), OpenAI API, Prompt engineering, json-repair

**Document Processing** — pdfplumber, python-docx, TXT ingestion

**Frontend** — Vanilla JavaScript, Responsive CSS, Drag-and-drop upload, Fetch API

**LaTeX & Resume Automation** — Section parsing, Deterministic rewrites, LLM rewrites, LaTeX sanitization, `.tex` download

**Testing** — pytest, Unit tests (matcher, LaTeX JSON, health)

**Tools & DevOps** — Git, GitHub, venv, pip, Vercel, `.env` configuration

**Concepts** — Resume–JD fit scoring, Skill overlap, Missing-skill detection, ATS optimization, Explainable NLP pipeline

## Build notes

Personal learnings while building this project (by module): [LEARNINGS.md](LEARNINGS.md)
