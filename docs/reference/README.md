# Reference material

## `resume-matcher-prototype.py`

The single-file Flask + spaCy resume matcher this project's matching engine
was ported from. Kept for provenance — it is **not** imported by anything and
is not on the Python path.

The live engine is `backend/matching/`:

| Prototype | Ported to | Notable changes |
| --- | --- | --- |
| `extract_text_from_pdf` / `_docx` | `matching/extraction.py` | Raises `ResumeParseError` instead of swallowing every exception and returning `""`; normalises PDF whitespace; reads DOCX tables |
| `find_experience_years` | `matching/extractors.py` | Durations stated next to the word "experience" win; the whole-document maximum is only a fallback |
| `find_education_levels` | `matching/extractors.py` | Bare abbreviations matched case-sensitively (the old `b\.?e\.?` matched the word "be"); "MS Office"/"MS SQL" no longer read as a master's degree |
| `MatchingEngine.semantic_similarity` | `matching/backends.py` | Pluggable backend; spaCy vectors averaged over content words only, which widened the score spread on the reference set from 0.06 to 0.16; TF-IDF fallback for machines without the model |
| `rank_candidates` | `matching/engine.py` (`screen`) | Returns ranked, below-threshold and hard-filter-excluded groups instead of silently dropping everyone who failed |
