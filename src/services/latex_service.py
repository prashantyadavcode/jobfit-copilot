import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx
from json_repair import repair_json

REWRITE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "rewrites": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["id", "title", "content"],
            },
        }
    },
    "required": ["rewrites"],
}


SECTION_PATTERN = re.compile(
    r"(?P<section_cmd>\\section\*?)\{(?P<title>[^}]+)\}(?P<body>.*?)(?=\\section\*?\{|$)",
    re.DOTALL,
)

# Commands that must not appear inside a rewritten section body (next-section leak).
NEXT_LATEX_BOUNDARY_RE = re.compile(
    r"(?:\\{2,}\\section\*?\{|\\section\*?\{|\\subsection\*?\{|\\chapter\*?\{|\\vspace\*?\{)",
    re.IGNORECASE,
)

JD_PROSE_RE = re.compile(
    r"key responsibilities|good to have|multilingual nlp|programming strong|"
    r"develop and implement nlp|collaborate with data scientists",
    re.IGNORECASE,
)

# Checked before fuzzy hints; keys are normalized lowercase tokens.
EXACT_SKILL_CATEGORY: dict[str, str] = {
    "azure": "backend",
    "gcp": "backend",
    "aws": "backend",
    "s3": "backend",
    "mlops": "backend",
    "bigquery": "backend",
    "docker": "backend",
    "git": "backend",
    "fastapi": "backend",
    "flask": "backend",
    "rasa": "nlp",
    "summarization": "nlp",
    "text classification": "nlp",
    "supervised learning": "machine learning",
    "model evaluation": "machine learning",
    "spacy": "nlp",
    "nltk": "nlp",
    "langchain": "nlp",
    "langgraph": "nlp",
    "transformers": "nlp",
    "hugging face": "nlp",
    "ner": "nlp",
    "python": "programming",
    "sql": "programming",
    "c++": "programming",
    "pytorch": "machine learning",
    "tensorflow": "machine learning",
    "keras": "machine learning",
    "scikit-learn": "machine learning",
    "scikit learn": "machine learning",
    "pandas": "data",
    "numpy": "data",
    "matplotlib": "data",
    "selenium": "data",
    "beautifulsoup": "data",
}

# Order matters: cloud/backend is checked before NLP to avoid mis-routing.
SKILL_CATEGORY_HINTS: dict[str, tuple[str, ...]] = {
    "programming": ("python", "sql", "c++", "java", "javascript"),
    "backend": ("fastapi", "flask", "rest api", "rest", "docker", "git", "aws", "gcp", "azure", "mlops", "s3", "bigquery"),
    "machine learning": ("scikit", "tensorflow", "pytorch", "keras", "forecasting", "lstm", "arima"),
    "nlp": ("spacy", "nltk", "ner", "transformer", "langchain", "langgraph", "rag", "llm", "generative", "rasa", "summarization", "tokenization", "pos tagging", "sentiment"),
    "data": ("pandas", "numpy", "matplotlib", "selenium", "beautifulsoup", "etl"),
}

SKILL_LINE_LABEL_HINTS: dict[str, tuple[str, ...]] = {
    "programming": ("programming",),
    "nlp": ("nlp", "generative"),
    "machine learning": ("machine learning", "deep learning"),
    "backend": ("backend", "deployment", "cloud"),
    "data": ("data processing", "tools"),
}

# Keywords in an experience bullet that suggest which missing skill fits there.
BULLET_CONTEXT_HINTS: dict[str, tuple[str, ...]] = {
    "programming": ("python", "script", "pipeline", "automat", "workflow", "code"),
    "nlp": (
        "nlp",
        "text",
        "spacy",
        "nltk",
        "transformer",
        "ner",
        "langchain",
        "rag",
        "token",
        "sentiment",
        "classification",
        "intent",
        "generative",
        "language",
    ),
    "machine learning": (
        "model",
        "machine learning",
        "scikit",
        "pytorch",
        "tensorflow",
        "forecast",
        "train",
        "f1-score",
        "cross-validation",
        "precision",
        "roc-auc",
        "inference",
    ),
    "backend": (
        "fastapi",
        "flask",
        "api",
        "rest",
        "backend",
        "deploy",
        "docker",
        "git",
        "container",
        "microservice",
        "cloud",
        "aws",
        "s3",
        "bigquery",
        "production",
    ),
    "data": ("pandas", "etl", "data", "warehouse", "mongodb", "database", "analytics"),
}


class LatexService:
    def __init__(
        self,
        llm_provider: str,
        ollama_base_url: str,
        ollama_model: str,
        latex_compiler: str,
        openai_api_key: str | None,
        openai_model: str,
    ) -> None:
        self.llm_provider = llm_provider.lower().strip()
        self.ollama_base_url = ollama_base_url.rstrip("/")
        self.ollama_model = ollama_model
        self.latex_compiler = latex_compiler
        self.openai_api_key = openai_api_key
        self.openai_model = openai_model

    def extract_sections(self, latex_code: str) -> list[dict[str, str]]:
        section_matches = self._extract_section_matches(latex_code)
        sections: list[dict[str, str]] = []
        for match in section_matches:
            sections.append(
                {
                    "id": match["id"],
                    "title": match["title"],
                    "header": match["header"],
                    "content": match["content"],
                }
            )
        return sections

    def _extract_section_matches(self, latex_code: str) -> list[dict[str, Any]]:
        sections: list[dict[str, Any]] = []
        idx = 0
        for match in SECTION_PATTERN.finditer(latex_code):
            if self._is_match_commented(latex_code, match.start()):
                continue
            section_cmd = match.group("section_cmd").strip()
            title = match.group("title").strip() or f"Section {idx + 1}"
            leading_comments = LatexService._extract_leading_comment_block(latex_code, match.start())
            full_body = match.group("body").strip()
            active_body = LatexService._extract_active_latex(full_body)
            sections.append(
                {
                    "id": f"section_{idx}",
                    "title": title,
                    "header": f"{section_cmd}{{{title}}}",
                    "content": active_body,
                    "full_body": full_body,
                    "commented_body": LatexService._extract_commented_latex(full_body),
                    "leading_comments": leading_comments,
                    "start": match.start(),
                    "end": match.end(),
                    "original_block": match.group(0).strip(),
                }
            )
            idx += 1
        return sections

    @staticmethod
    def _is_match_commented(text: str, match_start: int) -> bool:
        line_start = text.rfind("\n", 0, match_start) + 1
        prefix = text[line_start:match_start]
        return re.search(r"(?<!\\)%", prefix) is not None

    @staticmethod
    def _comment_block(text: str) -> str:
        lines = text.splitlines()
        return "\n".join("% " + line for line in lines) if lines else "% "

    async def rewrite_sections(
        self,
        latex_code: str,
        selected_section_ids: list[str],
        jd_text: str,
        missing_skills: list[str],
        matched_skills: list[str] | None = None,
        suggestions: list[str] | None = None,
    ) -> dict[str, Any]:
        matched_skills = matched_skills or []
        suggestions = suggestions or []
        sections = self.extract_sections(latex_code)
        selected_sections = [s for s in sections if s["id"] in selected_section_ids]
        if not selected_sections:
            return {"rewrites": [], "message": "No matching sections selected."}

        rewritten_sections: list[dict[str, str]] = []
        preserve_sections = [
            s for s in selected_sections if self._is_preserve_only_section(s["title"])
        ]
        experience_sections = [
            s
            for s in selected_sections
            if self._is_experience_section(s["title"]) and s not in preserve_sections
        ]
        projects_sections = [
            s
            for s in selected_sections
            if self._is_projects_section(s["title"])
            and s not in preserve_sections
            and s not in experience_sections
        ]
        other_sections = [
            s
            for s in selected_sections
            if s not in preserve_sections
            and s not in experience_sections
            and s not in projects_sections
        ]

        for section in preserve_sections:
            rewritten_sections.append(
                {
                    "id": section["id"],
                    "title": section["title"],
                    "content": self._rewrite_section_deterministic(
                        section,
                        missing_skills,
                        matched_skills,
                        jd_text,
                    ),
                }
            )

        for section in experience_sections:
            rewritten_sections.append(
                {
                    "id": section["id"],
                    "title": section["title"],
                    "content": self._rewrite_experience_enhanced(
                        section["content"],
                        missing_skills,
                        matched_skills,
                    ),
                }
            )

        for section in projects_sections:
            rewritten_sections.append(
                {
                    "id": section["id"],
                    "title": section["title"],
                    "content": self._rewrite_projects_enhanced(
                        section["content"],
                        missing_skills,
                        matched_skills,
                    ),
                }
            )

        if other_sections:
            prompt = self._build_prompt(other_sections, jd_text, missing_skills, suggestions)
            llm_rewrites = await self._rewrite_with_provider(prompt)
            section_by_id = {s["id"]: s for s in other_sections}
            for item in llm_rewrites:
                original = section_by_id.get(item["id"], {})
                title = item.get("title") or original.get("title", "")
                item["content"] = self._sanitize_rewrite_content(
                    item.get("content", ""),
                    section_title=title,
                    original_content=original.get("content", ""),
                    missing_skills=None,
                )
                rewritten_sections.append(item)

        merged_latex = self._merge_rewrites_into_latex(latex_code, rewritten_sections)
        message = self._rewrite_status_message(
            preserve_sections, experience_sections, projects_sections, other_sections
        )
        return {
            "rewrites": rewritten_sections,
            "merged_latex": merged_latex,
            "message": message,
        }

    @staticmethod
    def _is_preserve_only_section(title: str) -> bool:
        lowered = title.lower()
        return "skill" in lowered or "education" in lowered

    @staticmethod
    def _is_experience_section(title: str) -> bool:
        return "experience" in title.lower()

    @staticmethod
    def _is_projects_section(title: str) -> bool:
        lowered = title.lower()
        return "projects" in lowered or "project" in lowered

    @classmethod
    def _rewrite_section_deterministic(
        cls,
        section: dict[str, Any],
        missing_skills: list[str],
        matched_skills: list[str],
        jd_text: str,
    ) -> str:
        title = section["title"].lower()
        content = section["content"]
        if "skill" in title:
            return cls._rewrite_skills_deterministic(content, missing_skills)
        return cls._rewrite_education_deterministic(content, jd_text)

    @classmethod
    def _rewrite_experience_enhanced(
        cls,
        active_original: str,
        missing_skills: list[str],
        matched_skills: list[str],
    ) -> str:
        """Keep LaTeX headers; enhance \\item bullets with JD skills (added + \\textbf highlight)."""
        base = cls._extract_active_latex(active_original)
        if not base:
            return base

        remaining = [s for s in missing_skills if s.strip()]
        lines = base.splitlines()
        output: list[str] = []
        item_indices = [i for i, line in enumerate(lines) if line.strip().startswith("\\item")]

        for idx, line in enumerate(lines):
            if idx not in item_indices:
                output.append(line)
                continue
            enhanced, remaining = cls._enhance_experience_bullet(
                line,
                remaining,
                matched_skills,
            )
            output.append(enhanced)

        if remaining and item_indices:
            last_item_idx = item_indices[-1]
            pos = item_indices.index(last_item_idx)
            output[pos], _ = cls._enhance_experience_bullet(
                output[pos],
                remaining,
                matched_skills,
                max_additions=3,
            )

        return "\n".join(output)

    @staticmethod
    def _rewrite_status_message(
        preserve_sections: list[dict[str, Any]],
        experience_sections: list[dict[str, Any]],
        projects_sections: list[dict[str, Any]],
        other_sections: list[dict[str, Any]],
    ) -> str:
        titles = [s["title"].lower() for s in preserve_sections]
        parts: list[str] = []
        if any("skill" in t for t in titles):
            parts.append("skills updated (format preserved)")
        if any("education" in t for t in titles):
            parts.append("education preserved (LaTeX-safe)")
        if experience_sections:
            parts.append("experience bullets updated (JD skills added and highlighted)")
        if projects_sections:
            parts.append("projects bullets updated (JD skills added and highlighted)")
        if other_sections:
            parts.append("other sections rewritten with AI")
        return "; ".join(parts).capitalize() + "." if parts else "Sections rewritten successfully."

    @classmethod
    def _rewrite_projects_enhanced(
        cls,
        active_original: str,
        missing_skills: list[str],
        matched_skills: list[str],
    ) -> str:
        """
        Projects: preserve LaTeX/macros; update bullet-like lines by adding + highlighting skills.

        Supports:
        - \\item ...
        - \\resumeItem{...}{...}
        - \\resumeSubItem{...}{...}
        """
        base = cls._extract_active_latex(active_original)
        if not base:
            return base

        remaining = [s for s in missing_skills if s.strip()]
        lines = base.splitlines()
        output: list[str] = []

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("\\item"):
                enhanced, remaining = cls._enhance_experience_bullet(
                    line,
                    remaining,
                    matched_skills,
                    max_additions=2,
                )
                output.append(enhanced)
                continue

            macro_enhanced = cls._enhance_two_arg_macro_line(
                line,
                remaining,
                matched_skills,
                macros=("resumeItem", "resumeSubItem"),
            )
            if macro_enhanced is not None:
                new_line, remaining = macro_enhanced
                output.append(new_line)
                continue

            output.append(line)

        return "\n".join(output)

    @classmethod
    def _enhance_two_arg_macro_line(
        cls,
        line: str,
        missing_skills: list[str],
        matched_skills: list[str],
        macros: tuple[str, ...],
    ) -> tuple[str, list[str]] | None:
        """
        Enhance a line like \\resumeSubItem{Title}{Description}.
        Only touches the second argument (description).
        """
        stripped = line.strip()
        for macro in macros:
            pattern = re.compile(
                rf"(\\{macro}\{{(?P<title>[^}}]*)\}}\{{)(?P<body>.*?)(\}}\s*)$"
            )
            m = pattern.match(stripped)
            if not m:
                continue
            body = m.group("body")
            fake_item = "\\item " + body
            enhanced_item, remaining = cls._enhance_experience_bullet(
                fake_item,
                missing_skills,
                matched_skills,
                max_additions=2,
            )
            enhanced_body = enhanced_item[len("\\item ") :]
            new_line = f"{m.group(1)}{enhanced_body}{m.group(4)}"
            return new_line, remaining
        return None

    @classmethod
    def _rewrite_education_deterministic(cls, active_original: str, jd_text: str) -> str:
        """Education uses fragile LaTeX (\\hfill, nested braces) — keep structure, optional JD courses."""
        base = cls._extract_active_latex(active_original)
        if not base:
            return base
        return cls._append_jd_courses_to_education(base, jd_text)

    @classmethod
    def _append_jd_courses_to_education(cls, education: str, jd_text: str) -> str:
        jd_lower = jd_text.lower()
        course_catalog = [
            ("Deep Learning", "deep learning"),
            ("Natural Language Processing", "natural language processing"),
            ("Computer Vision", "computer vision"),
            ("MLOps", "mlops"),
            ("Cloud Computing", "cloud"),
        ]
        to_add = [
            label
            for label, key in course_catalog
            if key in jd_lower and key not in education.lower() and label.lower() not in education.lower()
        ]
        if not to_add:
            return education

        courses_pattern = re.compile(
            r"(\\textbf\{Relevant Courses:\}\s*)([^}]+)(?=\}\s*\})",
            re.IGNORECASE,
        )
        match = courses_pattern.search(education)
        if not match:
            return education

        existing = match.group(2).rstrip().rstrip(",")
        merged = f"{existing}, {', '.join(to_add)}"
        return education[: match.start(2)] + merged + education[match.end(2) :]

    @classmethod
    def _enhance_experience_bullet(
        cls,
        line: str,
        missing_skills: list[str],
        matched_skills: list[str],
        max_additions: int = 2,
    ) -> tuple[str, list[str]]:
        bullet_lower = line.lower()
        to_add: list[str] = []
        still_missing: list[str] = []

        for skill in missing_skills:
            if cls._skill_item_in_text(skill, line):
                continue
            if cls._skill_relevant_to_bullet(skill, bullet_lower):
                to_add.append(skill)
            else:
                still_missing.append(skill)

        updated = cls._bold_skills_in_bullet(line, matched_skills + missing_skills)

        if to_add:
            additions = to_add[:max_additions]
            placed = {a.lower() for a in additions}
            still_missing = [s for s in still_missing if s.lower() not in placed]
            bold_terms = ", ".join(f"\\textbf{{{cls._format_skill_token(s)}}}" for s in additions)
            clause = f" Applied {bold_terms} in this role."
            if updated.rstrip().endswith("."):
                updated = updated.rstrip()[:-1] + clause
            else:
                updated = updated.rstrip() + clause

        return updated, still_missing

    @classmethod
    def _skill_relevant_to_bullet(cls, skill: str, bullet_lower: str) -> bool:
        skill_cat = cls._pick_skill_category(skill.lower())
        bullet_cats = cls._bullet_categories(bullet_lower)
        if skill_cat in bullet_cats:
            return True
        if skill_cat == "backend" and skill.lower() in {"azure", "gcp", "aws", "mlops", "s3", "bigquery"}:
            return bool(bullet_cats & {"backend", "data"})
        if skill_cat == "nlp" and skill.lower() in {"rasa", "summarization"}:
            return "nlp" in bullet_cats
        return False

    @staticmethod
    def _bullet_categories(bullet_lower: str) -> set[str]:
        categories: set[str] = set()
        for category, hints in BULLET_CONTEXT_HINTS.items():
            if any(hint in bullet_lower for hint in hints):
                categories.add(category)
        return categories or {"backend"}

    @classmethod
    def _bold_skills_in_bullet(cls, line: str, skills: list[str]) -> str:
        if not line.strip().startswith("\\item"):
            return line
        updated = line
        seen: set[str] = set()
        for skill in skills:
            key = skill.lower().strip()
            if not key or key in seen:
                continue
            seen.add(key)
            for variant in cls._skill_highlight_variants(skill):
                updated = cls._bold_first_unbold_match(updated, variant)
        return updated

    @classmethod
    def _skill_highlight_variants(cls, skill: str) -> list[str]:
        token = cls._format_skill_token(skill)
        variants = [token]
        lowered = skill.lower()
        aliases = {
            "gcp": ["GCP", "Google Cloud Platform"],
            "aws": ["AWS", "AWS S3"],
            "nlp": ["NLP"],
            "ner": ["NER", "Named Entity Recognition"],
            "api": ["API", "REST APIs", "REST API"],
            "mlops": ["MLOps"],
            "llm": ["LLMs", "LLM"],
        }
        variants.extend(aliases.get(lowered, []))
        unique: list[str] = []
        seen: set[str] = set()
        for variant in variants:
            key = variant.lower()
            if key not in seen:
                seen.add(key)
                unique.append(variant)
        return sorted(unique, key=len, reverse=True)

    @staticmethod
    def _bold_first_unbold_match(text: str, term: str) -> str:
        if not term or len(term) < 2:
            return text
        escaped = re.escape(term)
        if re.match(r"^[a-z0-9]+$", term, re.IGNORECASE):
            pattern = re.compile(rf"\b{escaped}\b", re.IGNORECASE)
        else:
            pattern = re.compile(escaped, re.IGNORECASE)
        for match in pattern.finditer(text):
            if LatexService._inside_textbf(text, match.start()):
                continue
            original = match.group(0)
            return text[: match.start()] + f"\\textbf{{{original}}}" + text[match.end() :]
        return text

    @staticmethod
    def _inside_textbf(text: str, position: int) -> bool:
        before = text[:position]
        return before.rfind("\\textbf{") > before.rfind("}")

    @classmethod
    def _rewrite_skills_deterministic(cls, active_original: str, missing_skills: list[str]) -> str:
        """Skills: never call the LLM — only add missing JD skills into the user's existing lines."""
        base = cls._extract_active_latex(active_original)
        if not base:
            return base
        text = base
        if missing_skills:
            text = cls._inject_missing_skills(text, missing_skills)
        text = cls._rebalance_skill_categories(text)
        return cls._align_skills_line_endings(text, base)

    def _merge_rewrites_into_latex(self, latex_code: str, rewrites: list[dict[str, str]]) -> str:
        rewrite_by_id = {item["id"]: item for item in rewrites if "id" in item}
        section_matches = self._extract_section_matches(latex_code)
        if not section_matches:
            return latex_code

        merged = latex_code
        for section in reversed(section_matches):
            rewrite = rewrite_by_id.get(section["id"])
            if not rewrite:
                continue
            rewritten_content = rewrite.get("content", "").strip()
            leading_comments = (section.get("leading_comments") or "").rstrip()
            rewritten_block = f"{section['header']}\n\n{rewritten_content}".strip()
            if leading_comments:
                rewritten_block = f"{leading_comments}\n{rewritten_block}".strip()
            commented_body = section.get("commented_body", "").strip()
            if commented_body:
                rewritten_block = f"{rewritten_block}\n\n{commented_body}"
            merged = merged[: section["start"]] + rewritten_block + merged[section["end"] :]
        return merged

    @staticmethod
    def _extract_leading_comment_block(latex_code: str, section_start: int) -> str:
        """
        Capture consecutive comment lines immediately preceding a \\section{...}.

        This prevents section divider comments like:
          %-----------EDUCATION-----------------
        from being "eaten" by the previous section when we rewrite in-place.
        """
        if section_start <= 0:
            return ""
        before = latex_code[:section_start]
        lines = before.splitlines()
        if not lines:
            return ""

        collected: list[str] = []
        i = len(lines) - 1
        # Allow blank lines between comments and the section.
        while i >= 0 and lines[i].strip() == "":
            collected.append(lines[i])
            i -= 1
        while i >= 0 and lines[i].lstrip().startswith("%"):
            collected.append(lines[i])
            i -= 1
            while i >= 0 and lines[i].strip() == "":
                collected.append(lines[i])
                i -= 1

        block = "\n".join(reversed(collected)).rstrip()
        # Only keep "divider-like" blocks to avoid pulling normal comments from previous content.
        if not re.search(r"%\s*-{3,}|%\s*={3,}|%.*EDUCATION|%.*EXPERIENCE|%.*PROJECT", block, re.IGNORECASE):
            return ""
        return block

    def build_pdf_preview(self, latex_code: str) -> bytes:
        compiler = shutil.which(self.latex_compiler)
        if not compiler:
            raise ValueError(
                f"LaTeX compiler '{self.latex_compiler}' not found. Install MacTeX/BasicTeX to enable PDF preview."
            )

        with tempfile.TemporaryDirectory(prefix="resume_preview_") as temp_dir:
            workdir = Path(temp_dir)
            tex_path = workdir / "resume_preview.tex"
            pdf_path = workdir / "resume_preview.pdf"
            tex_path.write_text(latex_code, encoding="utf-8")

            command = [
                compiler,
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-output-directory",
                str(workdir),
                str(tex_path),
            ]
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            if result.returncode != 0 or not pdf_path.exists():
                error_tail = (result.stdout + "\n" + result.stderr).strip()[-1500:]
                raise ValueError(f"LaTeX compile failed. Check template/packages.\n{error_tail}")

            return pdf_path.read_bytes()

    async def _rewrite_with_provider(self, prompt: str) -> list[dict[str, str]]:
        if self.llm_provider == "openai":
            if not self.openai_api_key:
                raise ValueError("OPENAI_API_KEY is missing. Add it in .env and restart the server.")
            return await self._call_openai(prompt)
        return await self._call_ollama(prompt)

    def _build_prompt(
        self,
        selected_sections: list[dict[str, str]],
        jd_text: str,
        missing_skills: list[str],
        suggestions: list[str],
    ) -> str:
        skills_text = ", ".join(missing_skills) if missing_skills else "None"
        suggestions_text = "\n".join(f"- {item}" for item in suggestions) if suggestions else "- None"
        sections_text = "\n\n".join(
            f"[{section['id']}] {section['title']}\n{section['content']}"
            for section in selected_sections
        )
        has_skills_section = any("skill" in section["title"].lower() for section in selected_sections)
        skills_rules = ""
        if has_skills_section:
            skills_rules = (
                "Skills section rules (critical):\n"
                "- Keep the SAME structure as the original: one \\\\textbf{Category:} list per line, ending with \\\\\\\\ before each newline.\n"
                "- Use \\\\& (backslash-ampersand) between words in category names, never bare &, Ö, or Ð.\n"
                "- Add each missing skill ONCE, comma-separated on the best-matching existing category line.\n"
                "- Only add a new \\\\textbf{...} line if the skill truly fits no existing category.\n"
                "- NEVER repeat a category label before every skill (wrong: 'Cloud X: Azure Cloud X: GCP').\n"
                "- Use 'Technologies' or 'Tools' in category names, not 'Experience' (e.g. 'Cloud Technologies', not 'Cloud Experience').\n"
                "- List technologies only (Azure, GCP, Docker), not phrases like 'Cloud Experience: Azure'.\n"
                "- NEVER remove any skill or technology already in the user's LaTeX; only ADD missing JD skills.\n\n"
            )
        return (
            "You are an ATS-focused resume editor for LaTeX resumes.\n"
            "Rewrite ONLY the selected sections.\n"
            "NEVER remove content the user already wrote — only add missing JD skills or lightly rephrase.\n"
            "Keep truthful claims, concise impact bullets, and strong action verbs.\n"
            "Do not invent employers, degrees, dates, or metrics.\n"
            "Preserve LaTeX formatting compatibility and return valid plain text for section bodies only.\n"
            "The content field must contain ONLY the active section body — never include \\\\section{...}, \\\\vspace, commented-out lines, or text from other sections.\n"
            "Never paste job-description paragraphs; output LaTeX commands only (\\\\textbf, \\\\item, \\\\begin, etc.).\n"
            "When adding missing skills, append them to the best matching existing category line; do not create repetitive label prefixes.\n\n"
            f"{skills_rules}"
            "JSON rules (required):\n"
            "- Return ONLY a JSON object, no markdown fences or commentary.\n"
            "- Escape every backslash twice in content (e.g. \\\\textbf not \\textbf).\n"
            "- Use \\n for line breaks inside content strings; do not use raw newlines inside JSON strings.\n"
            "- In LaTeX text always write \\\\& for ampersands (e.g. 'NLP \\\\& Generative AI').\n"
            "- Escape double quotes inside content as \\\".\n\n"
            f"Job Description:\n{jd_text}\n\n"
            f"Missing skills to incorporate where accurate: {skills_text}\n\n"
            f"Improvement suggestions:\n{suggestions_text}\n\n"
            "Selected sections:\n"
            f"{sections_text}\n\n"
            "Return STRICT JSON with this shape:\n"
            '{"rewrites":[{"id":"section_0","title":"Experience","content":"...rewritten body..."}]}'
        )

    async def _call_openai(self, prompt: str) -> list[dict[str, str]]:
        headers = {
            "Authorization": f"Bearer {self.openai_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.openai_model,
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": prompt}],
                }
            ],
            "text": {"format": {"type": "json_object"}},
        }

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post("https://api.openai.com/v1/responses", headers=headers, json=payload)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                error_detail = response.text
                if response.status_code == 429:
                    raise ValueError(
                        "OpenAI rate limit/quota reached (429). Check billing, add credits, or try again later."
                    ) from exc
                if response.status_code == 401:
                    raise ValueError("OpenAI API key is invalid. Update OPENAI_API_KEY in .env and restart.") from exc
                if response.status_code == 403:
                    raise ValueError("OpenAI request forbidden (403). Verify project/key permissions.") from exc
                raise ValueError(f"OpenAI API error ({response.status_code}): {error_detail}") from exc
            data = response.json()

        raw_json = data.get("output", [{}])[0].get("content", [{}])[0].get("text", "{}")
        return self._parse_rewrites_json(raw_json)

    async def _call_ollama(self, prompt: str) -> list[dict[str, str]]:
        payload = {
            "model": self.ollama_model,
            "prompt": prompt,
            "stream": False,
            "format": REWRITE_JSON_SCHEMA,
        }
        async with httpx.AsyncClient(timeout=120) as client:
            try:
                response = await client.post(f"{self.ollama_base_url}/api/generate", json=payload)
                response.raise_for_status()
            except httpx.ConnectError as exc:
                raise ValueError(
                    "Ollama is not running. Start it with `ollama serve` and pull a model "
                    f"like `ollama pull {self.ollama_model}`."
                ) from exc
            except httpx.HTTPStatusError as exc:
                raise ValueError(f"Ollama error ({response.status_code}): {response.text}") from exc

        raw_text = response.json().get("response", "{}")
        return self._parse_rewrites_json(raw_text)

    @staticmethod
    def _extract_active_latex(content: str) -> str:
        """Keep only uncommented lines — ignores dead/legacy blocks the user commented out."""
        active: list[str] = []
        for line in content.splitlines():
            if line.strip().startswith("%"):
                continue
            active.append(line.rstrip())
        return re.sub(r"\n{3,}", "\n\n", "\n".join(active)).strip()

    @staticmethod
    def _extract_commented_latex(content: str) -> str:
        lines = [line for line in content.splitlines() if line.strip().startswith("%")]
        return "\n".join(lines).strip()

    @staticmethod
    def _sanitize_rewrite_content(
        content: str,
        section_title: str = "",
        original_content: str = "",
        missing_skills: list[str] | None = None,
    ) -> str:
        text = LatexService._extract_active_latex(content)
        if not text:
            return text

        text = LatexService._strip_section_header_from_body(text, section_title)
        text = LatexService._truncate_at_next_section_boundary(text)
        text = LatexService._normalize_escaped_line_breaks(text)
        text = LatexService._remove_jd_prose_and_invalid_blocks(text)
        text = LatexService._fix_malformed_latex_fragments(text)
        text = LatexService._restore_stripped_latex_commands(text)
        if section_title and "experience" in section_title.lower():
            text = LatexService._strip_projects_bleed_from_experience(text)
        text = text.replace(" Ö ", r" \& ").replace(" Ð ", r" \& ")
        text = text.replace(" ö ", r" \& ").replace(" ð ", r" \& ")
        text = re.sub(r"(?<!\\)&(?!\\)", r"\\&", text)
        text = re.sub(r"\\&\\&+", r"\\&", text)
        text = re.sub(r"\\textbf\{([^}]+?):\s+\}", r"\\textbf{\1:}", text)
        text = re.sub(r"Cloud\s+Experience", "Cloud Technologies", text, flags=re.IGNORECASE)
        text = LatexService._collapse_duplicate_category_labels(text)
        text = LatexService._dedupe_inline_skill_values(text)

        active_original = LatexService._extract_active_latex(original_content) if original_content else ""
        if active_original and (not text.strip() or LatexService._is_broken_latex_rewrite(text, active_original)):
            return active_original

        if text.endswith(r"\n"):
            text = text[:-2].rstrip()
        return text.rstrip()

    @staticmethod
    def _is_broken_latex_rewrite(rewritten: str, original: str) -> bool:
        if not rewritten.strip():
            return True
        if JD_PROSE_RE.search(rewritten):
            return True
        if re.search(r"leftmargin|itemsep|parsep", rewritten, re.IGNORECASE):
            return True
        if original.count("{") and rewritten.count("{") != rewritten.count("}"):
            return True
        if r"\hfill" in original and r"\hfill" not in rewritten and "hfill" not in rewritten:
            return True
        if r"\textit" in original and r"\textit" not in rewritten and "extit" in rewritten:
            return True
        if r"\\" in original and r"\\" not in rewritten:
            return True
        if "itemize" in original and "itemize" not in rewritten and r"\item" not in rewritten:
            return True
        if r"\&" in original and "&" in rewritten.replace(r"\&", ""):
            return True
        return False

    @staticmethod
    def _remove_jd_prose_and_invalid_blocks(content: str) -> str:
        lines: list[str] = []
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped:
                lines.append("")
                continue
            if stripped.startswith("%"):
                continue
            if JD_PROSE_RE.search(stripped):
                continue
            if "\\" not in stripped and len(stripped) > 60:
                continue
            if re.match(r"^[A-Za-z0-9\s&·\-]+:\s*$", stripped):
                continue
            if re.match(r"^\\begin\{itemize\}", stripped) and "\\item" not in content:
                continue
            if stripped in {r"\resumeSubHeadingListEnd", r"\resumeSubHeadingListStart"}:
                continue
            if re.match(r"^\\resumeSubHeadingList(Start|End)\s*\\\\?\s*$", stripped):
                continue
            lines.append(line)
        text = "\n".join(lines)
        text = re.sub(
            r"\\begin\{itemize\}[^\n]*\\{1,2}\s*(?=\\textbf)",
            "",
            text,
            flags=re.IGNORECASE,
        )
        return re.sub(r"\n{3,}", "\n\n", text).strip()

    @staticmethod
    def _fix_malformed_latex_fragments(content: str) -> str:
        text = re.sub(r",\s*\\\s+", ", ", content)
        text = re.sub(r"\bext\{\\&", r"\\textbf{", text)
        text = re.sub(r"\}\s*\\section\*?\{", r"}\n\n\\section{", text)
        text = re.sub(r"\\resumeSubHeadingListEnd\s*\\\\", r"\\resumeSubHeadingListEnd", text)
        text = re.sub(r",?\s*leftmargin=[^,\]]+[^\\]*", "", text, flags=re.IGNORECASE)
        text = re.sub(r",?\s*itemsep=[^,\]]+", "", text, flags=re.IGNORECASE)
        text = re.sub(r",?\s*parsep=[^,\]]+", "", text, flags=re.IGNORECASE)
        return text

    @staticmethod
    def _restore_stripped_latex_commands(content: str) -> str:
        """Repair common LLM damage where leading backslashes are dropped."""
        replacements = [
            (r"(?<![\\])hfill\b", r"\\hfill"),
            (r"(?<![\\])extit\{", r"\\textit{"),
            (r"(?<![\\])extbf\{", r"\\textbf{"),
            (r"(?<![\\])footnotesize\{", r"\\footnotesize{"),
            (r"(?<![\\])vspace\{", r"\\vspace{"),
            (r"\nitem\s", r"\n\\item "),
            (r"^item\s", r"\\item "),
        ]
        text = content
        for pattern, repl in replacements:
            text = re.sub(pattern, repl, text, flags=re.MULTILINE)
        return text

    @staticmethod
    def _strip_projects_bleed_from_experience(content: str) -> str:
        project_markers = (
            "avalanche",
            "stock predict",
            "stock forecasting",
            "geospatial analysis",
        )
        kept: list[str] = []
        for line in content.splitlines():
            lower = line.lower()
            if any(marker in lower for marker in project_markers):
                continue
            kept.append(line)
        return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()

    @staticmethod
    def _is_valid_skill_item(item: str) -> bool:
        cleaned = item.strip().strip(",").strip()
        if len(cleaned) < 2:
            return False
        if re.search(
            r"leftmargin|itemsep|parsep|begin\{itemize|resumeSub|textbf\{",
            cleaned,
            re.IGNORECASE,
        ):
            return False
        if re.match(r"^[A-Za-z\s&·]+$", cleaned) and cleaned.endswith(":"):
            return False
        return True

    @classmethod
    def _inject_missing_skills(cls, content: str, missing_skills: list[str]) -> str:
        lines = cls._parse_textbf_skill_lines(content)
        if not lines:
            return content

        for skill in missing_skills:
            skill_l = skill.lower().strip()
            if not skill_l:
                continue
            target_key = cls._pick_skill_category(skill_l)
            target = cls._find_line_for_skill_category(target_key, lines)
            if not target:
                target = max(lines, key=lambda line: len(line["items"]))
            if cls._skill_on_line(skill, target["items"]):
                continue
            target["items"].append(cls._format_skill_token(skill))

        return "\n\n".join(
            cls._format_textbf_skill_line(line["label"], line["items"], line["suffix"]) for line in lines
        )

    @staticmethod
    def _format_skill_token(skill: str) -> str:
        cleaned = skill.strip()
        if not cleaned:
            return cleaned
        acronyms = {"gcp", "aws", "nlp", "ner", "api", "sql", "etl", "mlops", "llm", "rag"}
        lowered = cleaned.lower()
        if lowered in acronyms:
            return lowered.upper()
        if cleaned.isupper() and len(cleaned) <= 6:
            return cleaned
        if " " in cleaned:
            return cleaned.title()
        return cleaned[0].upper() + cleaned[1:]

    @staticmethod
    def _pick_skill_category(skill: str) -> str:
        normalized = skill.lower().strip()
        if normalized in EXACT_SKILL_CATEGORY:
            return EXACT_SKILL_CATEGORY[normalized]
        for category, hints in SKILL_CATEGORY_HINTS.items():
            if any(hint in normalized for hint in hints):
                return category
        return "backend"

    @classmethod
    def _rebalance_skill_categories(cls, content: str) -> str:
        """Move skills onto the correct \\textbf category line (e.g. Azure -> Backend, not NLP)."""
        lines = cls._parse_textbf_skill_lines(content)
        if not lines:
            return content

        ordered_items: list[str] = []
        seen: set[str] = set()
        for line in lines:
            for item in line["items"]:
                key = item.lower()
                if key in seen:
                    continue
                seen.add(key)
                ordered_items.append(item)

        for line in lines:
            line["items"] = []

        for item in ordered_items:
            if not cls._is_valid_skill_item(item):
                continue
            category = cls._pick_skill_category(item.lower())
            target = cls._find_line_for_skill_category(category, lines)
            if not target:
                target = lines[0]
            target["items"].append(item)

        return "\n\n".join(
            cls._format_textbf_skill_line(line["label"], line["items"], line["suffix"])
            for line in lines
            if line["items"]
        )

    @staticmethod
    def _skill_on_line(skill: str, line_items: list[str]) -> bool:
        skill_l = skill.lower()
        for item in line_items:
            if skill_l == item.lower():
                return True
            if LatexService._skill_item_in_text(skill, item):
                return True
        return False

    @staticmethod
    def _find_line_for_skill_category(category: str, lines: list[dict[str, Any]]) -> dict[str, Any] | None:
        label_hints = SKILL_LINE_LABEL_HINTS.get(category, (category,))
        for line in lines:
            label = line["label_key"]
            if any(hint in label for hint in label_hints):
                return line
        return None

    @staticmethod
    def _skill_item_in_text(item: str, text: str) -> bool:
        item_l = item.lower().strip()
        text_l = text.lower()
        if re.match(r"^[a-z0-9 .+\-/&]+$", item_l):
            if re.search(rf"\b{re.escape(item_l)}\b", text_l):
                return True
        if item_l in text_l:
            return True
        words = [w for w in re.findall(r"[a-z0-9]+", item_l) if len(w) > 2]
        if not words:
            return bool(re.search(rf"\b{re.escape(item_l)}\b", text_l))
        matched = sum(1 for word in words if re.search(rf"\b{re.escape(word)}\b", text_l))
        return matched >= max(1, len(words) - 1)

    @staticmethod
    def _normalize_skill_label(label: str) -> str:
        return re.sub(r"\s+", " ", label.strip().rstrip(":").lower())

    @staticmethod
    def _parse_textbf_skill_lines(content: str) -> list[dict[str, Any]]:
        lines: list[dict[str, Any]] = []
        for chunk in re.split(r"(?=\\textbf\{)", content):
            chunk = chunk.strip()
            if not chunk.startswith(r"\textbf{"):
                continue
            match = re.match(
                r"\\textbf\{(?P<label>[^}]+)\}\s*(?P<values>.*)",
                chunk,
                flags=re.DOTALL | re.IGNORECASE,
            )
            if not match:
                continue
            values = match.group("values").strip()
            suffix_match = re.search(r"(\\{2,})\s*$", values)
            suffix = suffix_match.group(1) if suffix_match else r" \\"
            if suffix_match:
                values = values[: suffix_match.start()].strip().rstrip(",")
            items = [
                part.strip()
                for part in values.split(",")
                if part.strip() and LatexService._is_valid_skill_item(part.strip())
            ]
            label = match.group("label").strip()
            lines.append(
                {
                    "label": label,
                    "label_key": LatexService._normalize_skill_label(label),
                    "items": items,
                    "suffix": suffix,
                }
            )
        return lines

    @staticmethod
    def _find_matching_skill_line(
        label_key: str, lines_by_key: dict[str, dict[str, Any]]
    ) -> dict[str, Any] | None:
        if label_key in lines_by_key:
            return lines_by_key[label_key]
        for key, line in lines_by_key.items():
            if key in label_key or label_key in key:
                return line
        return None

    @staticmethod
    def _format_textbf_skill_line(label: str, items: list[str], suffix: str) -> str:
        clean_label = label.strip().rstrip(":")
        return f"\\textbf{{{clean_label}:}} {', '.join(items)} {suffix}".rstrip()

    @classmethod
    def _preserve_user_skills_content(cls, rewritten: str, original: str) -> str:
        """Keep every skill item from the user's original LaTeX; only add new ones from the rewrite."""
        orig_lines = cls._parse_textbf_skill_lines(original)
        if not orig_lines:
            return cls._preserve_loose_skill_tokens(rewritten, original)

        re_lines = cls._parse_textbf_skill_lines(rewritten)
        re_by_key = {line["label_key"]: line for line in re_lines}
        output: list[str] = []
        matched_re_keys: set[str] = set()

        for orig in orig_lines:
            re_line = cls._find_matching_skill_line(orig["label_key"], re_by_key)
            if re_line:
                matched_re_keys.add(re_line["label_key"])

            label = re_line["label"] if re_line else orig["label"]
            suffix = re_line["suffix"] if re_line else orig["suffix"]
            merged_items: list[str] = []
            seen: set[str] = set()

            for item in orig["items"]:
                key = item.lower()
                if key not in seen:
                    merged_items.append(item)
                    seen.add(key)

            if re_line:
                for item in re_line["items"]:
                    key = item.lower()
                    if key not in seen:
                        merged_items.append(item)
                        seen.add(key)

            output.append(cls._format_textbf_skill_line(label, merged_items, suffix))

        for re_line in re_lines:
            if re_line["label_key"] in matched_re_keys:
                continue
            if any(
                re_line["label_key"] in ok or ok in re_line["label_key"]
                for ok in {o["label_key"] for o in orig_lines}
            ):
                continue
            output.append(cls._format_textbf_skill_line(re_line["label"], re_line["items"], re_line["suffix"]))

        result = "\n\n".join(output) if output else rewritten
        return cls._rebalance_skill_categories(result)

    @staticmethod
    def _category_for_label(label_key: str) -> str:
        for category, hints in SKILL_LINE_LABEL_HINTS.items():
            if any(hint in label_key for hint in hints):
                return category
        return ""

    @staticmethod
    def _preserve_loose_skill_tokens(rewritten: str, original: str) -> str:
        """Fallback when skills are not structured with \\textbf lines."""
        rewritten_lower = rewritten.lower()
        missing_chunks: list[str] = []
        for chunk in re.split(r",|\n|\\\\", original):
            token = chunk.strip().strip("%").strip()
            if len(token) < 3:
                continue
            if token.lower() not in rewritten_lower:
                missing_chunks.append(token)
        if not missing_chunks:
            return rewritten
        return rewritten.rstrip() + "\n\n% Restored from your original resume\n" + ", ".join(missing_chunks)

    @staticmethod
    def _strip_section_header_from_body(content: str, section_title: str) -> str:
        if not section_title:
            return content.strip()
        pattern = rf"^\\section\*?\{{\s*{re.escape(section_title)}\s*\}}\s*"
        return re.sub(pattern, "", content, count=1, flags=re.IGNORECASE).lstrip()

    @staticmethod
    def _truncate_at_next_section_boundary(content: str) -> str:
        match = NEXT_LATEX_BOUNDARY_RE.search(content)
        if not match:
            return content
        return content[: match.start()].rstrip().rstrip("\\").rstrip()

    @staticmethod
    def _normalize_escaped_line_breaks(content: str) -> str:
        """Turn JSON/LaTeX artifacts like \\\\n or \\n into real newlines between skill lines."""
        text = re.sub(r"\\{2,}n(?![A-Za-z])", "\n", content)
        text = re.sub(r"(?<!\\)\\n(?![A-Za-z])", "\n", text)
        return text

    @staticmethod
    def _collapse_duplicate_category_labels(content: str) -> str:
        """Merge 'Label: A Label: B' into 'Label: A, B' when the same label repeats."""
        pattern = re.compile(
            r"(?P<prefix>(?:\\textbf\{)?)(?P<label>[^}:]+?):\s*"
            r"(?P<val>[^:]+?)\s+(?P=prefix)(?P=label):\s*",
            flags=re.IGNORECASE,
        )
        changed = True
        while changed:
            changed = False
            match = pattern.search(content)
            if not match:
                break
            prefix = match.group("prefix")
            label = match.group("label").strip()
            val = match.group("val").strip().rstrip(",")
            replacement = f"{prefix}{label}: {val}, "
            content = content[: match.start()] + replacement + content[match.end() :]
            changed = True
        return content

    @staticmethod
    def _dedupe_inline_skill_values(content: str) -> str:
        """Remove duplicate comma-separated tokens inside a category value span."""
        def dedupe_values(match: re.Match[str]) -> str:
            prefix, label, values = match.group(1), match.group(2), match.group(3)
            parts = [part.strip() for part in values.split(",") if part.strip()]
            seen: set[str] = set()
            unique: list[str] = []
            for part in parts:
                key = part.lower()
                if key in seen:
                    continue
                seen.add(key)
                unique.append(part)
            return f"{prefix}{label}: {', '.join(unique)}"

        return re.sub(
            r"((?:\\textbf\{)?)([^}:]+?):\s*([^\\]+?)(?=\\\\|\n|\Z)",
            dedupe_values,
            content,
            flags=re.IGNORECASE,
        )

    @staticmethod
    def _align_skills_line_endings(content: str, original_content: str) -> str:
        """Ensure skill lines end with LaTeX line breaks like the source section."""
        original_uses_double_slash = "\\\\" in original_content
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        normalized: list[str] = []
        for line in lines:
            if line.startswith("%"):
                normalized.append(line)
                continue
            line = line.rstrip()
            if original_uses_double_slash:
                line = line.rstrip("\\").rstrip()
                if not line.endswith("\\\\"):
                    line = f"{line} \\\\"
            normalized.append(line)
        return "\n\n".join(normalized)

    @staticmethod
    def _extract_json_payload(raw_text: str) -> str:
        text = raw_text.strip()
        if not text:
            return "{}"
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
        if fence_match:
            text = fence_match.group(1).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1]
        return text

    @staticmethod
    def _coerce_rewrites(parsed: Any) -> list[dict[str, str]]:
        if not isinstance(parsed, dict):
            return []
        rewrites = parsed.get("rewrites", [])
        if not isinstance(rewrites, list):
            return []
        return [
            {
                "id": str(item["id"]),
                "title": str(item["title"]),
                "content": str(item["content"]),
            }
            for item in rewrites
            if isinstance(item, dict) and all(k in item for k in ("id", "title", "content"))
        ]

    @classmethod
    def _parse_rewrites_json(cls, raw_json: str) -> list[dict[str, str]]:
        payload = cls._extract_json_payload(raw_json)
        last_error: json.JSONDecodeError | None = None
        for candidate in (payload, repair_json(payload)):
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError as exc:
                last_error = exc
                continue
            rewrites = cls._coerce_rewrites(parsed)
            if rewrites:
                return rewrites

        fallback = cls._parse_rewrites_fallback(payload)
        if fallback:
            return fallback

        hint = (
            "The AI response was not valid JSON (often caused by LaTeX backslashes or unescaped newlines). "
            "Try rewriting one section at a time, simplify LaTeX in that section, or use OpenAI in .env."
        )
        if last_error:
            raise ValueError(f"{hint} Details: {last_error}") from last_error
        raise ValueError(f"{hint} No rewrites could be parsed.")

    @staticmethod
    def _parse_rewrites_fallback(text: str) -> list[dict[str, str]]:
        """Extract rewrite objects when the outer JSON envelope is broken."""
        rewrites: list[dict[str, str]] = []
        for match in re.finditer(
            r'"id"\s*:\s*"(?P<id>[^"\\]*(?:\\.[^"\\]*)*)"\s*,\s*'
            r'"title"\s*:\s*"(?P<title>[^"\\]*(?:\\.[^"\\]*)*)"\s*,\s*'
            r'"content"\s*:\s*"(?P<content>(?:[^"\\]|\\.)*)"\s*\}',
            text,
            flags=re.DOTALL,
        ):
            rewrites.append(
                {
                    "id": bytes(match.group("id"), "utf-8").decode("unicode_escape"),
                    "title": bytes(match.group("title"), "utf-8").decode("unicode_escape"),
                    "content": bytes(match.group("content"), "utf-8").decode("unicode_escape"),
                }
            )
        return rewrites
