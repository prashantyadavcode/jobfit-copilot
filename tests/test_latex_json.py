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
    # Invalid JSON: single backslash before textbf; repair_json should recover structure.
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
