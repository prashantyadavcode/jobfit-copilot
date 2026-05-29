"""Vercel build hook: verify spaCy model is available before deploy."""

from __future__ import annotations

import sys


def main() -> None:
    try:
        import spacy

        spacy.load("en_core_web_sm")
    except OSError as exc:
        print(
            "spaCy model en_core_web_sm is missing. "
            "Install it via requirements.txt or run: python -m spacy download en_core_web_sm",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    print("spaCy model en_core_web_sm is ready.")


if __name__ == "__main__":
    main()
