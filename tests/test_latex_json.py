import pytest

from src.services.latex_service import LatexService


def test_parse_rewrites_json_valid():
    raw = '{"rewrites":[{"id":"section_0","title":"Skills","content":"Python, NLP"}]}'
    result = LatexService._parse_rewrites_json(raw)
    assert len(result) == 1
    assert result[0]["id"] == "section_0"
    assert "Python" in result[0]["content"]


def test_parse_rewrites_json_with_markdown_fence():
    raw = """```json
{"rewrites":[{"id":"section_1","title":"Experience","content":"Led API work"}]}
```"""
    result = LatexService._parse_rewrites_json(raw)
    assert result[0]["id"] == "section_1"


def test_parse_rewrites_json_repairs_latex_backslashes():
    raw = (
        '{"rewrites":[{"id":"section_0","title":"Skills",'
        '"content":"\\textbf{Python} and \\textit{NLP} with Docker"}]}'
    )
    result = LatexService._parse_rewrites_json(raw)
    assert result[0]["id"] == "section_0"
    assert "Python" in result[0]["content"]


def test_parse_rewrites_json_raises_when_unrecoverable():
    with pytest.raises(ValueError, match="not valid JSON"):
        LatexService._parse_rewrites_json("not json at all")


def test_sanitize_fixes_mojibake_ampersands():
    bad = r"\textbf{NLP Ö Generative AI:} spaCy \\ \textbf{Data Processing Ð Tools:} Pandas \n"
    fixed = LatexService._sanitize_rewrite_content(bad, section_title="Skills")
    assert "Ö" not in fixed
    assert "Ð" not in fixed
    assert r"\&" in fixed
    assert not fixed.endswith(r"\n")


def test_sanitize_collapses_repeated_cloud_labels():
    bad = r"\textbf{Cloud Experience:} Azure \textbf{Cloud Experience:} GCP \textbf{Cloud Experience:} MLOps"
    fixed = LatexService._sanitize_rewrite_content(bad, section_title="Skills")
    assert "Cloud Technologies" in fixed
    assert fixed.lower().count("cloud technologies:") == 1
    assert "Azure" in fixed and "GCP" in fixed


def test_sanitize_dedupes_repeated_skill_tokens():
    bad = r"\textbf{Cloud Technologies:} Azure, GCP, GCP, MLOps \\"
    fixed = LatexService._sanitize_rewrite_content(bad, section_title="Skills")
    assert fixed.count("GCP") == 1


def test_sanitize_strips_leaked_next_section():
    bad = (
        r"\section{Skills}"
        r"\textbf{Programming: } Python \\"
        r"\textbf{Data Processing \& Tools: } Pandas \\\section{Experience} \vspace{5pt}"
    )
    fixed = LatexService._sanitize_rewrite_content(bad, section_title="Skills")
    assert "Experience" not in fixed
    assert "vspace" not in fixed
    assert "Programming" in fixed


def test_sanitize_fixes_triple_backslash_n_between_lines():
    bad = r"\textbf{Programming:} Python, C++\\\n\textbf{NLP \& Generative AI:} spaCy"
    fixed = LatexService._sanitize_rewrite_content(bad, section_title="Skills")
    assert r"\\\n" not in fixed
    assert "NLP" in fixed


def test_preserve_user_skills_keeps_original_items():
    original = (
        r"\textbf{Programming:} Python, SQL, C++ \\"
        r"\textbf{NLP \& Generative AI:} spaCy, NLTK, LangChain \\"
    )
    rewritten = (
        r"\textbf{Programming:} Python \\"
        r"\textbf{NLP \& Generative AI:} spaCy, Rasa \\"
    )
    merged = LatexService._preserve_user_skills_content(rewritten, original)
    assert "SQL" in merged
    assert "C++" in merged
    assert "NLTK" in merged
    assert "LangChain" in merged
    assert "Rasa" in merged


def test_extract_active_latex_ignores_comments():
    raw = (
        "% old skills\n"
        r"\textbf{Programming:} Python \\"
        "\n% \textbf{Legacy:} COBOL"
    )
    active = LatexService._extract_active_latex(raw)
    assert "Python" in active
    assert "COBOL" not in active
    assert "old skills" not in active


def test_remove_jd_prose_from_projects_rewrite():
    bad = (
        "Key Responsibilities Develop and implement NLP models for text processing "
        "and understanding Build end-to-end NLP pipelines"
    )
    cleaned = LatexService._remove_jd_prose_and_invalid_blocks(bad)
    assert "Key Responsibilities" not in cleaned
    assert cleaned == ""


def test_deterministic_skills_keeps_all_original_items():
    original = r"\textbf{Programming:} Python, SQL, C++ \\"
    fixed = LatexService._rewrite_skills_deterministic(original, [])
    assert "SQL" in fixed
    assert "C++" in fixed
    assert "Python" in fixed


def test_rebalance_moves_cloud_skills_out_of_nlp_line():
    content = (
        r"\textbf{Programming:} Python, SQL \\"
        r"\textbf{NLP \& Generative AI:} spaCy, Azure, GCP, Rasa, Summarization \\"
        r"\textbf{Backend \& Deployment:} FastAPI, Docker \\"
    )
    fixed = LatexService._rebalance_skill_categories(content)
    nlp_line = [line for line in fixed.split("\n\n") if "NLP" in line][0]
    backend_line = [line for line in fixed.split("\n\n") if "Backend" in line][0]
    assert "Azure" in backend_line
    assert "GCP" in backend_line
    assert "Rasa" in nlp_line
    assert "Summarization" in nlp_line
    assert "Azure" not in nlp_line


EDUCATION_SAMPLE = r"""
\vspace{5pt}
\textbf{Guru Gobind Singh Indraprastha University} \hfill {Pitampura, India} \\
Bachelor of Technology - Artificial Intelligence \& Machine Learning \hfill {2021 - 2025} \\
CGPA: 8.98/10.0 \\
\textit{\footnotesize{\textbf{Relevant Courses:} Advances in Machine Learning, Data Mining, Statistics, DBMS}}
""".strip()


EXPERIENCE_SAMPLE = r"""
\textbf{Kaidoko Automation Solutions Private Limited} \hfill {New Delhi} \\
\textit{Machine Learning Engineer (Full-time)} \hfill {Feb 2025 - Present} \\

\begin{itemize}[leftmargin=0.5cm, itemsep=1pt, parsep=2pt]
\item Developed and maintained end-to-end NLP and ML workflows for a confidential EdTech client.
\item Built scalable text-processing pipelines using spaCy, NLTK, and Hugging Face Transformers.
\end{itemize}
""".strip()


def test_experience_enhanced_adds_and_highlights_skills():
    sample = EXPERIENCE_SAMPLE + (
        "\n\\item Containerized ML applications using Docker, managed version control through Git, "
        "and utilized AWS S3 and Google BigQuery for scalable data storage."
    )
    result = LatexService._rewrite_experience_enhanced(
        sample,
        missing_skills=["azure", "gcp", "rasa"],
        matched_skills=["python", "docker", "fastapi"],
    )
    assert r"\item Developed" in result
    deploy_line = [line for line in result.splitlines() if "Docker" in line and "\\item" in line][0]
    assert r"\textbf{Docker}" in deploy_line
    assert "Azure" in deploy_line or "GCP" in deploy_line
    assert r"\textbf{Rasa}" in result or "Applied \\textbf{Rasa}" in result


def test_restore_stripped_latex_commands():
    broken = "textbf{Kaidoko} hfill {New Delhi} \\\ntextit{Engineer}"
    fixed = LatexService._restore_stripped_latex_commands(broken)
    assert r"\hfill" in fixed
    assert r"\textit{" in fixed
    assert r"\textbf{" in fixed


def test_education_deterministic_preserves_hfill_and_ampersand():
    result = LatexService._rewrite_education_deterministic(EDUCATION_SAMPLE, "")
    assert r"\hfill" in result
    assert r"\&" in result
    assert "Guru Gobind Singh" in result
    assert "CGPA" in result


def test_education_appends_jd_courses_when_relevant():
    jd = "Looking for deep learning and NLP experience."
    result = LatexService._rewrite_education_deterministic(EDUCATION_SAMPLE, jd)
    assert "Deep Learning" in result or "deep learning" in result.lower()


def test_sanitize_falls_back_to_original_for_broken_education_llm_output():
    broken = "Bachelor of Technology - Artificial Intelligence & Machine Learning 2021 - 2025"
    fixed = LatexService._sanitize_rewrite_content(
        broken,
        section_title="Education",
        original_content=EDUCATION_SAMPLE,
    )
    assert r"\hfill" in fixed
    assert r"\&" in fixed


def test_leading_section_divider_comment_is_preserved_before_education():
    latex = r"""
\section{Summary}
Hello

%-----------EDUCATION-----------------
\section{Education}
\vspace{5pt}
\textbf{University} \hfill {City} \\
""".strip()

    service = LatexService(
        llm_provider="ollama",
        ollama_base_url="http://127.0.0.1:11434",
        ollama_model="llama3.2:3b",
        latex_compiler="pdflatex",
        openai_api_key=None,
        openai_model="gpt-4.1-mini",
    )
    rewrites = [
        {"id": "section_0", "title": "Summary", "content": "Hello updated"},
        {
            "id": "section_1",
            "title": "Education",
            "content": r"\vspace{5pt}\n\textbf{University} \hfill {City} \\",
        },
    ]
    merged = service._merge_rewrites_into_latex(latex, rewrites)
    assert "%-----------EDUCATION-----------------" in merged
    assert merged.index("%-----------EDUCATION-----------------") < merged.index(r"\section{Education}")


def test_deterministic_skills_preserves_textbf_format():
    original = (
        r"\textbf{Programming:} Python, SQL, C++ \\"
        r"\textbf{NLP \& Generative AI:} spaCy, NLTK \\"
        r"\textbf{Backend \& Deployment:} FastAPI, Docker \\"
    )
    result = LatexService._rewrite_skills_deterministic(original, ["azure", "gcp", "rasa"])
    assert r"\textbf{Programming:}" in result
    assert r"\textbf{NLP \& Generative AI:}" in result
    assert "Azure" in result
    assert "GCP" in result
    assert "Rasa" in result
    assert "NLP Generative AI:\n" not in result
    assert "leftmargin" not in result


def test_inject_missing_skills_adds_to_backend_line():
    content = (
        r"\textbf{Programming:} Python, SQL \\"
        r"\textbf{Backend \& Deployment:} FastAPI, Docker \\"
    )
    merged = LatexService._inject_missing_skills(content, ["azure", "gcp"])
    assert "Azure" in merged or "azure" in merged
    assert "GCP" in merged or "gcp" in merged
    assert "FastAPI" in merged
