from src.nlp.extractor import ResumeJDExtractor
from src.services.matcher_service import MatcherService


class AnalyzerService:
    def __init__(self, spacy_model: str = 'en_core_web_sm'):
        self.extractor = ResumeJDExtractor(spacy_model=spacy_model)
        self.matcher = MatcherService()

    def analyze(self, resume_text: str, jd_text: str) -> dict:
        resume_data = self.extractor.extract(resume_text)
        jd_data = self.extractor.extract(jd_text)
        match = self.matcher.compute_match(resume_data, jd_data)

        return {
            'score': match.score,
            'matched_skills': match.matched_skills,
            'missing_skills': match.missing_skills,
            'suggestions': match.suggestions,
            'resume_summary': {
                'skills_found': len(resume_data['skills']),
                'top_terms': resume_data['top_terms'][:10],
            },
            'jd_summary': {
                'skills_required': len(jd_data['skills']),
                'top_terms': jd_data['top_terms'][:10],
            },
        }
