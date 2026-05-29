from dataclasses import dataclass

from rapidfuzz import fuzz


@dataclass
class MatchResult:
    score: float
    matched_skills: list[str]
    missing_skills: list[str]
    suggestions: list[str]


class MatcherService:
    def compute_match(self, resume_data: dict, jd_data: dict) -> MatchResult:
        resume_skills = set(s.lower() for s in resume_data.get('skills', []))
        jd_skills = set(s.lower() for s in jd_data.get('skills', []))

        matched = sorted(resume_skills & jd_skills)
        missing = sorted(jd_skills - resume_skills)

        if not jd_skills:
            score = 0.0
        else:
            overlap_score = len(matched) / len(jd_skills) * 100
            semantic_score = fuzz.token_set_ratio(
                ' '.join(resume_data.get('top_terms', [])),
                ' '.join(jd_data.get('top_terms', [])),
            )
            score = round(0.7 * overlap_score + 0.3 * semantic_score, 2)

        suggestions = [
            f'Add "{s}" to the best matching skills/tools category (comma-separated, no repeated labels)'
            for s in missing[:8]
        ]
        return MatchResult(score, matched, missing, suggestions)
