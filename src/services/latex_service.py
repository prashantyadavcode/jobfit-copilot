import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx


SECTION_PATTERN = re.compile(
    r"(?P<section_cmd>\\section\*?)\{(?P<title>[^}]+)\}(?P<body>.*?)(?=\\section\*?\{|$)",
    re.DOTALL,
)


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
            sections.append(
                {
                    "id": f"section_{idx}",
                    "title": title,
                    "header": f"{section_cmd}{{{title}}}",
                    "content": match.group("body").strip(),
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
        suggestions: list[str],
    ) -> dict[str, Any]:
        sections = self.extract_sections(latex_code)
        selected_sections = [s for s in sections if s["id"] in selected_section_ids]
        if not selected_sections:
            return {"rewrites": [], "message": "No matching sections selected."}

        prompt = self._build_prompt(selected_sections, jd_text, missing_skills, suggestions)
        rewritten_sections = await self._rewrite_with_provider(prompt)
        merged_latex = self._merge_rewrites_into_latex(latex_code, rewritten_sections)
        return {
            "rewrites": rewritten_sections,
            "merged_latex": merged_latex,
            "message": "Sections rewritten successfully.",
        }

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
            rewritten_block = f"{section['header']}\n\n{rewritten_content}".strip()
            replacement = (
                "% Original section kept for reference\n"
                f"{self._comment_block(section['original_block'])}\n\n"
                "% Rewritten section\n"
                f"{rewritten_block}"
            )
            merged = merged[: section["start"]] + replacement + merged[section["end"] :]
        return merged

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
        return (
            "You are an ATS-focused resume editor for LaTeX resumes.\n"
            "Rewrite ONLY the selected sections.\n"
            "Keep truthful claims, concise impact bullets, and strong action verbs.\n"
            "Do not invent employers, degrees, dates, or metrics.\n"
            "Preserve LaTeX formatting compatibility and return valid plain text for section bodies only.\n\n"
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
            "format": "json",
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
    def _parse_rewrites_json(raw_json: str) -> list[dict[str, str]]:
        parsed = json.loads(raw_json)
        rewrites = parsed.get("rewrites", [])
        return [r for r in rewrites if all(k in r for k in ("id", "title", "content"))]
