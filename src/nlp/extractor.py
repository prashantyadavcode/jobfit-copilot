import re
from collections import Counter

import spacy

from src.utils.text_utils import clean_text

SKILL_KEYWORDS = {
    'python', 'sql', 'fastapi', 'flask', 'spacy', 'nltk', 'pytorch', 'tensorflow',
    'transformers', 'docker', 'aws', 'gcp', 'azure', 'mlops', 'rasa', 'nlp',
    'machine learning', 'deep learning', 'ner', 'summarization', 'classification'
}


class ResumeJDExtractor:
    def __init__(self, spacy_model: str = 'en_core_web_sm'):
        self.nlp = spacy.load(spacy_model)

    def extract(self, text: str) -> dict:
        text = clean_text(text)
        doc = self.nlp(text)
        tokens = [t.lemma_.lower() for t in doc if t.is_alpha]
        lowered = text.lower()

        found_skills = sorted([s for s in SKILL_KEYWORDS if s in lowered])
        entities = [{'text': e.text, 'label': e.label_} for e in doc.ents]

        years = re.findall(r'(\d+)\+?\s+years?', lowered)
        top_terms = [w for w, _ in Counter(tokens).most_common(20)]

        return {
            'skills': found_skills,
            'entities': entities,
            'years_of_experience_mentions': years,
            'top_terms': top_terms,
            'text_length': len(text),
        }
