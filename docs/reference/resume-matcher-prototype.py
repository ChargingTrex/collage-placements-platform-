# matching/engine.py
#
# Resume parsing & semantic matching engine for the Placement Cell Portal.
#
# Ported from the resume-matcher-app-Arun Flask prototype
# (https://github.com/ChargingTrex/resume-matcher-app-Arun). The original
# app bundled text extraction, regex-based extractors, and spaCy semantic
# similarity into a single-file Flask+Jinja UI. This module keeps the same
# extraction/scoring logic but strips out Flask, HTML templates, and file
# I/O side effects so it can be called as a plain service from:
#   - the Student Profile app (resume upload -> pre-fill experience/education)
#   - the Opportunities Board app (rank student profiles against a posting)
#   - the Certification Suggestions app (score a student's skill text against
#     certification descriptions to find the best gap-filling match)
#
# Install:
#   pip install PyPDF2 python-docx spacy
#   python -m spacy download en_core_web_md
#
# This module has no Django imports so it can be unit-tested standalone;
# wire it into Django views/tasks by importing MatchingEngine.

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

import PyPDF2
import docx
import spacy
from spacy.language import Language

DEFAULT_SPACY_MODEL = "en_core_web_md"
DEFAULT_SIMILARITY_THRESHOLD = 0.60

UG_PATTERNS = [
    r"bachelor\s*of\s*technology",
    r"bachelor\s*of\s*engineering",
    r"\b(b\.?e\.?|b\.?tech\.?|b\.?sc\.?|bca|bba)\b",
    r"\b(bachelor|undergraduate|diploma)\b",
]
MASTERS_PATTERNS = [
    r"master\s*of\s*science",
    r"master\s*of\s*technology",
    r"\b(m\.?s\.?|m\.?e\.?|m\.?tech\.?|mca|mba)\b",
    r"\b(master|postgraduate|pg\s*diploma)\b",
]
PG_PATTERNS = [
    r"\b(ph\.?d|doctorate|doctoral)\b",
]


# --- Text extraction -------------------------------------------------------

def extract_text_from_pdf(file_obj) -> str:
    """Extract text from a PDF file-like object (bytes or an open file)."""
    try:
        reader = PyPDF2.PdfReader(file_obj)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text
        return text
    except Exception:
        return ""


def extract_text_from_docx(file_obj) -> str:
    """Extract text from a DOCX file-like object (bytes or an open file)."""
    try:
        document = docx.Document(file_obj)
        return "\n".join(paragraph.text for paragraph in document.paragraphs)
    except Exception:
        return ""


def extract_text(file_obj, filename: str) -> str:
    """Dispatch to the right extractor based on the file extension."""
    extension = filename.rsplit(".", 1)[-1].lower()
    if extension == "pdf":
        return extract_text_from_pdf(file_obj)
    if extension == "docx":
        return extract_text_from_docx(file_obj)
    raise ValueError(f"Unsupported resume file type: .{extension}")


# --- Regex-based extractors --------------------------------------------------

def find_experience_years(text: str) -> float:
    """Return the maximum years of experience mentioned in free text."""
    year_matches = re.findall(r"(\d+\.?\d*)\s*\+?\s*years?", text, re.IGNORECASE)
    month_matches = re.findall(r"(\d+)\s*\+?\s*months?", text, re.IGNORECASE)

    total_experience = 0.0
    if year_matches:
        total_experience = max(float(num) for num in year_matches)
    if month_matches:
        total_experience += max(float(num) for num in month_matches) / 12.0
    return round(total_experience, 1)


def find_education_levels(text: str) -> set[str]:
    """Return the set of education levels ({'UG', 'Masters', 'PG'}) found in text."""
    found: set[str] = set()
    text_lower = text.lower()

    if any(re.search(pattern, text_lower) for pattern in UG_PATTERNS):
        found.add("UG")
    if any(re.search(pattern, text_lower) for pattern in MASTERS_PATTERNS):
        found.add("Masters")
    if any(re.search(pattern, text_lower) for pattern in PG_PATTERNS):
        found.add("PG")
    return found


# --- Result types -------------------------------------------------------

@dataclass
class ExtractedProfile:
    """What the engine pulls out of one resume, used to pre-fill a student profile."""
    raw_text: str
    experience_years: float
    education_levels: set[str] = field(default_factory=set)


@dataclass
class MatchResult:
    """One candidate's score against a single target text (job description,
    opportunity, or certification description)."""
    identifier: str  # e.g. student id, filename, or profile id
    similarity_score: float
    passed_threshold: bool
    extracted: ExtractedProfile


# --- The engine -------------------------------------------------------

class MatchingEngine:
    """
    Loads the spaCy model once and exposes parsing + semantic scoring.
    Instantiate a single MatchingEngine per process (e.g. as a Django
    app-level singleton or via a management command / Celery worker
    warm-up) since loading the spaCy model is the expensive part.
    """

    def __init__(self, model_name: str = DEFAULT_SPACY_MODEL):
        try:
            self.nlp: Optional[Language] = spacy.load(model_name)
        except OSError as exc:
            raise RuntimeError(
                f"spaCy model '{model_name}' not found. "
                f"Run: python -m spacy download {model_name}"
            ) from exc

    # -- parsing --------------------------------------------------------

    def parse_resume(self, file_obj, filename: str) -> ExtractedProfile:
        """Extract text, experience, and education from one resume file."""
        text = extract_text(file_obj, filename)
        return ExtractedProfile(
            raw_text=text,
            experience_years=find_experience_years(text) if text else 0.0,
            education_levels=find_education_levels(text) if text else set(),
        )

    # -- scoring ----------------------------------------------------------

    def semantic_similarity(self, text_a: str, text_b: str) -> float:
        """Cosine similarity between two texts using spaCy doc vectors."""
        if not text_a or not text_b:
            return 0.0
        doc_a = self.nlp(text_a, disable=["parser", "ner"])
        doc_b = self.nlp(text_b, disable=["parser", "ner"])
        return round(doc_a.similarity(doc_b), 3)

    def score_one(
        self,
        identifier: str,
        candidate_text: str,
        target_text: str,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        min_experience_years: Optional[float] = None,
        required_education: Optional[Iterable[str]] = None,
    ) -> MatchResult:
        """
        Score one candidate (resume text, profile summary, or skills blob)
        against one target text (job description, opportunity requirements,
        or certification description), applying optional hard filters.
        """
        extracted = ExtractedProfile(
            raw_text=candidate_text,
            experience_years=find_experience_years(candidate_text),
            education_levels=find_education_levels(candidate_text),
        )

        if min_experience_years is not None and extracted.experience_years < min_experience_years:
            return MatchResult(identifier, 0.0, False, extracted)

        if required_education:
            required = set(required_education)
            if not required.issubset(extracted.education_levels):
                return MatchResult(identifier, 0.0, False, extracted)

        score = self.semantic_similarity(candidate_text, target_text)
        return MatchResult(identifier, score, score >= similarity_threshold, extracted)

    def rank_candidates(
        self,
        candidates: dict[str, str],
        target_text: str,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        min_experience_years: Optional[float] = None,
        required_education: Optional[Iterable[str]] = None,
    ) -> list[MatchResult]:
        """
        Bulk-score a pool of candidates (identifier -> text, e.g. student_id ->
        resume/profile text) against one target text. Returns only candidates
        that pass the hard filters and the similarity threshold, sorted by
        score descending -- the shape both the Opportunities Board ranking
        and the Certification Suggestions matching use.
        """
        results = [
            self.score_one(
                identifier,
                text,
                target_text,
                similarity_threshold=similarity_threshold,
                min_experience_years=min_experience_years,
                required_education=required_education,
            )
            for identifier, text in candidates.items()
        ]
        passed = [r for r in results if r.passed_threshold]
        return sorted(passed, key=lambda r: r.similarity_score, reverse=True)


# --- Example usage (not run in production; for reference / smoke testing) --

if __name__ == "__main__":
    engine = MatchingEngine()

    job_description = (
        "Looking for a backend engineer with 2+ years experience in Python, "
        "Django, and PostgreSQL. Bachelor's degree required."
    )

    sample_profiles = {
        "student_101": "3 years experience with Python, Django REST Framework, "
                        "and PostgreSQL. B.Tech in Computer Science.",
        "student_102": "6 months internship experience in frontend React work. "
                       "Currently pursuing BCA.",
    }

    ranked = engine.rank_candidates(
        candidates=sample_profiles,
        target_text=job_description,
        similarity_threshold=0.55,
        min_experience_years=1.0,
        required_education={"UG"},
    )

    for result in ranked:
        print(
            f"{result.identifier}: score={result.similarity_score} "
            f"experience={result.extracted.experience_years}y "
            f"education={sorted(result.extracted.education_levels)}"
        )
