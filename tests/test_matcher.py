from src.services.matcher_service import MatcherService


def test_matcher_scores_overlap():
    svc = MatcherService()
    resume_data = {'skills': ['python', 'fastapi', 'nlp'], 'top_terms': ['python', 'api', 'nlp']}
    jd_data = {'skills': ['python', 'nlp', 'docker'], 'top_terms': ['python', 'docker', 'nlp']}
    result = svc.compute_match(resume_data, jd_data)
    assert result.score > 50
    assert 'python' in result.matched_skills
    assert 'docker' in result.missing_skills
