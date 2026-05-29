# What I Learned While Building JobFit Copilot

Notes I wrote for myself while building this project — one section per part of the codebase.

---

## Resume & JD parsing (`src/services/parser_service.py`)

I learned that PDF text is messy: `pdfplumber` page-by-page extraction is good enough for ATS-style resumes, and DOCX is simpler with `python-docx`. Keeping one `parse_file()` entry point by file extension made the API layer much cleaner.

---

## Skill extraction (`src/nlp/extractor.py`)

I started with spaCy `en_core_web_sm` for lemmas and NER, plus a curated skill keyword list. Real resumes rarely use perfect grammar, so matching skills as substrings in lowered text worked better than relying only on NER labels. NLTK stopwords/punkt setup is boring but necessary on a fresh machine.

---

## Match scoring (`src/services/matcher_service.py`)

My first version was only set overlap on skills. That felt too harsh when wording differed. I blended **70% skill overlap** with **30% RapidFuzz token similarity** on top terms — small change, much more realistic scores. Missing skills became concrete rewrite suggestions instead of a bare list.

---

## FastAPI app (`app/main.py`)

I kept routes thin and pushed logic into services. `POST /analyze/mixed` (file + pasted JD) matched how I actually use the UI. Mounting `StaticFiles` and serving `index.html` at `/` meant one `uvicorn` command for demo and development.

---

## Frontend (`app/static/`)

I built the UI without a framework first: drag-and-drop upload, enabling the analyze button only when resume + JD exist, and hiding result panels until analysis finishes. That taught me how much state the UX needs even for a “simple” form. Panel cards + ocean blue accents kept it readable without a component library.

---

## LaTeX section parsing (`latex_service.py` — extraction)

`\section{...}` regex parsing breaks if you ignore commented lines. I added `_extract_active_latex()` to skip `%` lines so old commented blocks do not pollute rewrites. Divider comments like `%-----------EDUCATION-----------------` must stay above the section — `_extract_leading_comment_block()` only keeps divider-style comment blocks so normal comments are not stolen from the previous section.

---

## LaTeX — why Skills skip the LLM

The LLM kept mangling `\textbf{}` lines, duplicating categories, and dropping backslashes. I stopped calling the model for Skills and only **inject missing JD skills** into existing `\textbf{...}` lines. I map skills to categories (Azure/GCP → backend, Rasa/summarization → NLP) with exact tokens first, then fuzzy hints — order matters so cloud tools do not land under NLP.

---

## LaTeX — Education & Experience

Education uses `\hfill` and nested braces; the LLM broke those often. I keep Education deterministic and only append JD-relevant courses when it fits. Experience/Projects bullets get `\textbf{skill}` highlights and short “Applied …” clauses from missing skills, using bullet context keywords so “api” does not match inside “Solutions”.

---

## LaTeX — JSON from Ollama

Local `llama3.2:3b` often returns invalid JSON because of LaTeX backslashes and literal `\n`. I use `json-repair`, strip markdown fences, and a regex fallback to pull `id` / `title` / `content` objects when the envelope is broken. Sanitization fixes `Ö`/`Ð` ampersand corruption, restores dropped `\hfill` / `\textbf`, and truncates at the next `\section` so the model does not leak the whole resume into one section.

---

## LaTeX — merge back into the file

Rewriting in place is safer than appending giant “original commented” blocks. I replace only the active body, keep `leading_comments` and `commented_body`, and merge from the end of the file backward so indices stay valid.

---

## Testing (`tests/`)

I added tests when LaTeX bugs kept coming back: JSON repair, skill category rebalance, experience bullet enhancement, education preservation, and merge behavior. pytest gave me confidence to change sanitization without fear of regressions.

---

## Config & LLM providers (`.env`, `src/core/config.py`)

Ollama locally is free and good for demos; OpenAI is optional when I need more reliable JSON. Making the provider swappable in settings taught me to keep prompts and parsing separate from transport (`httpx` to Ollama vs OpenAI API).
