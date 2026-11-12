"""
Write one synthetic transcript PDF per fixture kind (clean, tampered, ...).

    python manage.py make_sample_transcripts
    python manage.py make_sample_transcripts --out /some/dir

Everything is invented. PRNs follow YY0200NNN with YY = batch - 4.
"""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from checkpoints.transcript_fixtures import CASES, make_case

DEFAULT_OUT = Path(settings.BASE_DIR) / "fixtures" / "transcripts"

# Batch 2026 -> YY 22; sequences 930-949 are reserved for synthetic students.
SAMPLE_PRN_BASE = "220200"
FIRST_SEQUENCE = 930


class Command(BaseCommand):
    help = "Write synthetic transcript PDFs, one per fixture kind."

    def add_arguments(self, parser):
        parser.add_argument("--out", default=str(DEFAULT_OUT), help="Output directory.")

    def handle(self, *args, **options):
        out_dir = Path(options["out"])
        out_dir.mkdir(parents=True, exist_ok=True)
        for offset, kind in enumerate(CASES):
            prn = f"{SAMPLE_PRN_BASE}{FIRST_SEQUENCE + offset}"
            path = make_case(kind, out_dir, prn=prn, name=f"Sample Student {offset + 1}")
            self.stdout.write(f"{kind}: {path} (PRN {prn})")
