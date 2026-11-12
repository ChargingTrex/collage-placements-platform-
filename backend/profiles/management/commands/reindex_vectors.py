"""
Re-embed analysed profiles into the vector store.

    python manage.py reindex_vectors                # every analysed profile
    python manage.py reindex_vectors --dirty-only   # form changed, or a new EMBED_MODEL
    python manage.py reindex_vectors --prn 220200921

Needs the LLM server, which makes the embeddings. Only profiles whose
analysis is done are indexed: a vector without a reading would carry
filters nothing has checked.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from matching.embeddings import get_embedder
from profiles.analysis import index_profile
from profiles.models import ResumeAnalysis


class Command(BaseCommand):
    help = "Re-embed analysed student profiles into the vector store."

    def add_arguments(self, parser):
        parser.add_argument("--prn", help="One student's profile.")
        parser.add_argument(
            "--dirty-only",
            action="store_true",
            help="Only profiles changed since indexing, or indexed by another embedding model.",
        )

    def handle(self, *args, prn=None, dirty_only=False, **options):
        embedder = get_embedder()
        if embedder is None:
            raise CommandError("The LLM is disabled (LLM_ENABLED); nothing can be embedded.")

        analyses = (
            ResumeAnalysis.objects.filter(status=ResumeAnalysis.Status.DONE)
            .exclude(Q(profile__resume="") | Q(profile__resume=None))
            .select_related("profile__student")
            .order_by("profile__student__prn")
        )
        if prn:
            analyses = analyses.filter(profile__student__prn=prn)
            if not analyses.exists():
                raise CommandError(f"No analysed resume for PRN {prn}.")
        if dirty_only:
            # A vector from another model shares no space with the new ones.
            analyses = analyses.filter(Q(needs_reindex=True) | ~Q(embedding_model=embedder.model))

        done = failed = 0
        for analysis in analyses.iterator():
            if index_profile(analysis.profile, analysis, embedder):
                done += 1
            else:
                failed += 1
                self.stderr.write(f"{analysis.profile.prn}: embedding failed; left marked for reindex.")
        self.stdout.write(self.style.SUCCESS(f"Reindexed {done}; {failed} failed."))
