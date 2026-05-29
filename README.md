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
pip install -r requirements.txt
python -m spacy download en_core_web_sm
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

## API
- `POST /analyze/text` -> analyze plain text resume + JD
- `POST /analyze/files` -> analyze uploaded resume + JD file
- `POST /analyze/mixed` -> analyze uploaded resume + pasted JD

## Why this stands out for NLP roles
- End-to-end NLP pipeline
- Production API design with file ingestion
- Practical model outputs with explainable matching
- Deployment-ready structure
