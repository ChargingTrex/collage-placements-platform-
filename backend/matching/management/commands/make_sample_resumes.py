"""
Render the reference resumes in `matching/samples.py` into real PDF and DOCX
files, so the file-parsing path is exercised against actual binaries rather
than against strings.

    python manage.py make_sample_resumes
    python manage.py make_sample_resumes --out /tmp/resumes

The files are generated, not committed -- `.gitignore` excludes them, and
this command recreates them from the text that carries the expected values.
"""

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from matching.samples import SAMPLE_JOB_DESCRIPTION, SAMPLE_RESUMES

DEFAULT_OUT = Path(settings.BASE_DIR) / "fixtures" / "resumes"


def write_pdf(path: Path, lines: list[str]) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    width, height = A4
    pdf = canvas.Canvas(str(path), pagesize=A4)
    pdf.setFont("Helvetica", 10.5)

    y = height - 60
    for line in lines:
        if y < 60:  # new page
            pdf.showPage()
            pdf.setFont("Helvetica", 10.5)
            y = height - 60
        pdf.drawString(56, y, line)
        y -= 15
    pdf.save()


def write_docx(path: Path, lines: list[str]) -> None:
    import docx

    document = docx.Document()
    for line in lines:
        document.add_paragraph(line)
    document.save(str(path))


def render_samples(out_dir: Path) -> list[Path]:
    """Write every sample resume into `out_dir`. Returns the paths written."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []

    for sample in SAMPLE_RESUMES:
        path = out_dir / sample.filename
        if sample.format == "pdf":
            write_pdf(path, list(sample.lines))
        else:
            write_docx(path, list(sample.lines))
        written.append(path)

    (out_dir / "job_description.txt").write_text(SAMPLE_JOB_DESCRIPTION, encoding="utf-8")

    # The hand-checked reference, in a form a human can diff against.
    reference = {
        sample.filename: {
            "experience_years": sample.expected_experience_years,
            "education_levels": sorted(sample.expected_education_levels),
            "relevant_to_job_description": sample.relevant,
            **({"age": sample.expected_age} if sample.expected_age is not None else {}),
            **({"cgpa": sample.expected_cgpa} if sample.expected_cgpa is not None else {}),
        }
        for sample in SAMPLE_RESUMES
    }
    (out_dir / "reference.json").write_text(
        json.dumps(reference, indent=2) + "\n", encoding="utf-8"
    )
    return written


class Command(BaseCommand):
    help = "Generate the sample PDF/DOCX resumes used by the Phase 2 checkpoint."

    def add_arguments(self, parser):
        parser.add_argument("--out", default=str(DEFAULT_OUT))

    def handle(self, *args, **options):
        out_dir = Path(options["out"])
        written = render_samples(out_dir)
        for path in written:
            self.stdout.write(f"  {path.name:<36} {path.stat().st_size:>7} bytes")
        self.stdout.write(
            self.style.SUCCESS(
                f"Wrote {len(written)} resumes, job_description.txt and "
                f"reference.json to {out_dir}"
            )
        )
