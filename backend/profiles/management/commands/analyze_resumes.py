"""
Run the full resume analysis outside a request: the backfill path.

    python manage.py analyze_resumes --all            # every profile with a resume
    python manage.py analyze_resumes --prn 220200921  # one student
    python manage.py analyze_resumes --all --force    # even when already current

An analysis already current for its resume text is skipped, so re-running
after an outage only redoes what fell back to regex or never ran. The time
budget applies per resume, exactly as in the request.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from profiles.analysis import analyse
from profiles.models import StudentProfile


class Command(BaseCommand):
    help = "Analyse stored resumes with the LLM (when enabled), embed and index them."

    def add_arguments(self, parser):
        scope = parser.add_mutually_exclusive_group(required=True)
        scope.add_argument("--all", action="store_true", help="Every profile with a resume.")
        scope.add_argument("--prn", help="One student's profile.")
        parser.add_argument("--force", action="store_true", help="Re-run current analyses too.")

    def handle(self, *args, all=False, prn=None, force=False, **options):
        profiles = (
            StudentProfile.objects.exclude(Q(resume="") | Q(resume=None))
            .select_related("student")
            .order_by("student__prn")
        )
        if prn:
            profiles = profiles.filter(student__prn=prn)
            if not profiles.exists():
                raise CommandError(f"No profile with a resume for PRN {prn}.")

        ran = skipped = 0
        for profile in profiles.iterator():
            analysis, did_run = analyse(profile, force=force)
            if did_run:
                ran += 1
                self.stdout.write(f"{profile.prn}: {analysis.status} ({analysis.source or '-'})")
            else:
                skipped += 1
        self.stdout.write(self.style.SUCCESS(f"Analysed {ran}; {skipped} already up to date."))
