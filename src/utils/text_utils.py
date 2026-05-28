import re


def clean_text(text: str) -> str:
    text = text.replace('\u00ad', '')
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
